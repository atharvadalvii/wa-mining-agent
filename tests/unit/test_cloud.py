from pathlib import Path

import pytest

from geoagent import cloud


class FakeS3:
    """Just enough of the boto3 S3 client for geoagent.cloud."""

    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.downloaded: list[str] = []
        self.uploads: list[tuple[str, str, str]] = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        outer = self

        class _Paginator:
            def paginate(self, Bucket, Prefix):
                keys = [k for k in outer.objects if k.startswith(Prefix)]
                # Two pages, to exercise pagination.
                half = max(len(keys) // 2, 1)
                for chunk in (keys[:half], keys[half:]):
                    yield {"Contents": [{"Key": k, "Size": len(outer.objects[k])} for k in chunk]}

        return _Paginator()

    def download_file(self, bucket, key, filename):
        self.downloaded.append(key)
        Path(filename).write_bytes(self.objects[key])

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.uploads.append((bucket, key, (ExtraArgs or {}).get("ContentType", "")))

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://{Params['Bucket']}.s3.example/{Params['Key']}?exp={ExpiresIn}"


def _objects():
    return {
        "data/local_network/drive_nodes.parquet": b"aaaa",
        "data/local_network/drive_edges.parquet": b"bb",
        "data/local_network/walk_nodes.parquet": b"cc",
        "data/local_network/bike_nodes.parquet": b"dddddddd",
        "data/local_network/README.txt": b"ignore me",
        "data/osm_extracts/western-australia-latest.osm.pbf": b"pbfpbf",
    }


def test_sync_downloads_only_the_requested_network_types_plus_the_pbf(tmp_path):
    tables, pbf = tmp_path / "tables", tmp_path / "pbf"
    s3 = FakeS3(_objects())
    fetched = cloud.sync_data_from_s3(
        "s3://bucket/data",
        dest=tables,
        pbf_dest=pbf,
        network_types=("drive", "walk"),
        client=s3,
    )
    assert sorted(fetched) == [
        "drive_edges.parquet",
        "drive_nodes.parquet",
        "walk_nodes.parquet",
        "western-australia-latest.osm.pbf",
    ]
    assert not (tables / "bike_nodes.parquet").exists()
    assert not (tables / "README.txt").exists()
    assert (tables / "drive_nodes.parquet").read_bytes() == b"aaaa"
    assert (pbf / "western-australia-latest.osm.pbf").read_bytes() == b"pbfpbf"


def test_sync_skips_files_already_present_at_the_same_size(tmp_path):
    (tmp_path / "drive_nodes.parquet").write_bytes(b"aaaa")  # same size as S3's copy
    s3 = FakeS3(_objects())
    fetched = cloud.sync_data_from_s3(
        "s3://bucket/data", dest=tmp_path, pbf_dest=tmp_path, network_types=("drive",), client=s3
    )
    assert sorted(fetched) == ["drive_edges.parquet", "western-australia-latest.osm.pbf"]


def test_sync_redownloads_a_truncated_file(tmp_path):
    (tmp_path / "drive_nodes.parquet").write_bytes(b"a")  # interrupted earlier download
    fetched = cloud.sync_data_from_s3(
        "s3://bucket/data",
        dest=tmp_path,
        pbf_dest=tmp_path,
        network_types=("drive",),
        client=FakeS3(_objects()),
    )
    assert "drive_nodes.parquet" in fetched
    assert (tmp_path / "drive_nodes.parquet").read_bytes() == b"aaaa"


@pytest.mark.parametrize("uri", ["https://x/y", "s3://", "bucket/prefix"])
def test_sync_rejects_malformed_uris(uri, tmp_path):
    with pytest.raises(ValueError):
        cloud.sync_data_from_s3(uri, dest=tmp_path, client=FakeS3({}))


def test_publish_map_returns_a_presigned_link(tmp_path):
    f = tmp_path / "route-a-to-b.html"
    f.write_text("<html></html>")
    s3 = FakeS3({})
    url = cloud.publish_map(f, bucket="maps-bucket", client=s3)
    assert url.startswith("https://maps-bucket.s3.example/maps/route-a-to-b.html")
    assert s3.uploads == [("maps-bucket", "maps/route-a-to-b.html", "text/html; charset=utf-8")]


def test_publish_map_without_a_bucket_returns_the_local_path(tmp_path, monkeypatch):
    monkeypatch.delenv("GEOAGENT_MAPS_S3_BUCKET", raising=False)
    f = tmp_path / "m.html"
    assert cloud.publish_map(f) == str(f)


def test_publish_map_falls_back_to_the_path_if_the_upload_fails(tmp_path):
    class Broken:
        def upload_file(self, *a, **k):
            raise RuntimeError("AccessDenied")

    f = tmp_path / "m.html"
    assert cloud.publish_map(f, bucket="b", client=Broken()) == str(f)


class FakeHfEntry:
    def __init__(self, path, size):
        self.path, self.size = path, size


class FakeHfApi:
    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def list_repo_tree(self, repo_id, path_in_repo, repo_type):
        assert repo_type == "dataset"
        return [
            FakeHfEntry(p, len(b)) for p, b in self.files.items() if p.startswith(path_in_repo + "/")
        ]


def _hf_files():
    return {
        "local_network/drive_nodes.parquet": b"aaaa",
        "local_network/drive_edges.parquet": b"bb",
        "local_network/bike_nodes.parquet": b"dddddddd",
        "local_network/README.md": b"dataset card",
        "osm_extracts/western-australia-latest.osm.pbf": b"pbfpbf",
    }


def _fake_download(files, calls):
    def download(repo_id, repo_type, filename, local_dir):
        calls.append(filename)
        out = Path(local_dir) / filename  # hf_hub_download keeps the repo-relative path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(files[filename])

    return download


def test_hf_sync_lands_files_in_the_expected_directories(tmp_path):
    files, calls = _hf_files(), []
    tables, pbf = tmp_path / "cache" / "local_network", tmp_path / "data" / "osm_extracts"
    fetched = cloud.sync_data_from_hf(
        "someone/wa-street-data",
        dest=tables,
        pbf_dest=pbf,
        network_types=("drive",),
        api=FakeHfApi(files),
        download=_fake_download(files, calls),
    )
    assert sorted(fetched) == [
        "drive_edges.parquet",
        "drive_nodes.parquet",
        "western-australia-latest.osm.pbf",
    ]
    assert (tables / "drive_nodes.parquet").read_bytes() == b"aaaa"
    assert (pbf / "western-australia-latest.osm.pbf").read_bytes() == b"pbfpbf"
    assert not (tables / "bike_nodes.parquet").exists()
    assert not (tables / "README.md").exists()


def test_hf_sync_skips_files_already_present_at_the_same_size(tmp_path):
    files, calls = _hf_files(), []
    tables, pbf = tmp_path / "cache" / "local_network", tmp_path / "data" / "osm_extracts"
    tables.mkdir(parents=True)
    (tables / "drive_nodes.parquet").write_bytes(b"aaaa")
    fetched = cloud.sync_data_from_hf(
        "someone/wa-street-data",
        dest=tables,
        pbf_dest=pbf,
        network_types=("drive",),
        api=FakeHfApi(files),
        download=_fake_download(files, calls),
    )
    assert "drive_nodes.parquet" not in fetched
    assert "local_network/drive_nodes.parquet" not in calls

"""Tests for Kaggle dateCreated on variations."""

from __future__ import annotations

from datetime import datetime
import unittest

from etl.assets.kaggle_transformation import normalize_kaggle_instance
from etl_extractors.kaggle.clients.instances_client import KaggleInstancesClient
from etl_extractors.kaggle.kaggle_crawler import KaggleCrawler
from etl_extractors.kaggle.kaggle_helper import KaggleHelper


class TestParseKaggleDatetime(unittest.TestCase):
    def test_meta_kaggle_us_datetime(self):
        parsed = KaggleHelper.parse_kaggle_datetime("01/11/2023 19:46:42")
        assert parsed == datetime(2023, 1, 11, 19, 46, 42)

    def test_iso_date(self):
        parsed = KaggleHelper.parse_kaggle_datetime("2023-01-11")
        assert parsed == datetime(2023, 1, 11)

    def test_empty(self):
        assert KaggleHelper.parse_kaggle_datetime("") is None
        assert KaggleHelper.parse_kaggle_datetime(None) is None


class TestAttachMetaDates(unittest.TestCase):
    def test_fills_missing_creation_date(self):
        crawler = KaggleCrawler(output_dir="/tmp/kaggle-date-test")
        records = [{"ref": "google/bert", "title": "BERT"}]
        attached = crawler.attach_meta_dates(
            records, {"google/bert": "01/11/2023 19:46:42"}
        )
        assert attached == 1
        assert records[0]["CreationDate"] == "01/11/2023 19:46:42"

    def test_does_not_overwrite_publish_time(self):
        crawler = KaggleCrawler(output_dir="/tmp/kaggle-date-test")
        records = [{"ref": "google/bert", "publishTime": "2020-01-01T00:00:00Z"}]
        attached = crawler.attach_meta_dates(
            records, {"google/bert": "01/11/2023 19:46:42"}
        )
        assert attached == 0
        assert "CreationDate" not in records[0]


class TestVariationDateCreated(unittest.TestCase):
    def test_instance_row_copies_parent_creation_date(self):
        client = KaggleInstancesClient({"data": [], "timestamp": "2026-01-01"})
        rows = client.fetch_instances_metadata(
            {
                "ref": "google/bert",
                "title": "BERT",
                "author": "Google",
                "CreationDate": "01/11/2023 19:46:42",
                "instances": [
                    {
                        "framework": "tensorFlow2",
                        "slug": "default",
                        "url": (
                            "https://www.kaggle.com/models/google/"
                            "bert/TensorFlow2/default"
                        ),
                    }
                ],
            }
        )
        assert rows[0]["dateCreated"] == "01/11/2023 19:46:42"
        assert rows[0]["dateModified"] == "01/11/2023 19:46:42"

    def test_instance_row_prefers_update_time(self):
        client = KaggleInstancesClient({"data": [], "timestamp": "2026-01-01"})
        rows = client.fetch_instances_metadata(
            {
                "ref": "google/bert",
                "title": "BERT",
                "author": "Google",
                "CreationDate": "01/11/2023 19:46:42",
                "lastUpdateTime": "2024-06-01T12:00:00Z",
                "instances": [
                    {
                        "framework": "tensorFlow2",
                        "slug": "default",
                        "url": (
                            "https://www.kaggle.com/models/google/"
                            "bert/TensorFlow2/default"
                        ),
                    }
                ],
            }
        )
        assert rows[0]["dateCreated"] == "01/11/2023 19:46:42"
        assert rows[0]["dateModified"] == "2024-06-01T12:00:00Z"

    def test_normalize_parses_parent_date(self):
        mapped = normalize_kaggle_instance(
            {
                "instanceId": "google/bert/TensorFlow2/default",
                "mlentory_id": "https://w3id.org/mlentory/mlentory_graph/abc",
                "url": "https://www.kaggle.com/models/google/bert/TensorFlow2/default",
                "name": "BERT (TensorFlow2)",
                "frameworkName": "TensorFlow2",
                "dateCreated": "01/11/2023 19:46:42",
            }
        )
        assert mapped["dateCreated"] == datetime(2023, 1, 11, 19, 46, 42)
        assert mapped["datePublished"] == mapped["dateCreated"]
        assert mapped["dateModified"] == mapped["dateCreated"]
        assert mapped["extraction_metadata"]["dateCreated"]["source_field"] == (
            "CreationDate, publishTime"
        )

    def test_normalize_keeps_distinct_modified_date(self):
        mapped = normalize_kaggle_instance(
            {
                "instanceId": "google/bert/TensorFlow2/default",
                "mlentory_id": "https://w3id.org/mlentory/mlentory_graph/abc",
                "url": "https://www.kaggle.com/models/google/bert/TensorFlow2/default",
                "name": "BERT (TensorFlow2)",
                "frameworkName": "TensorFlow2",
                "dateCreated": "01/11/2023 19:46:42",
                "dateModified": "2024-06-01T12:00:00Z",
            }
        )
        assert mapped["dateCreated"] == datetime(2023, 1, 11, 19, 46, 42)
        assert mapped["dateModified"] == KaggleHelper.parse_kaggle_datetime(
            "2024-06-01T12:00:00Z"
        )
        assert mapped["extraction_metadata"]["dateModified"]["source_field"] == (
            "updateTime, CreationDate"
        )

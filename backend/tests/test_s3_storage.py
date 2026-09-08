import s3_storage


class _RecordingS3Client:
    def __init__(self):
        self.request = None

    def put_object(self, **kwargs):
        self.request = kwargs


def test_private_upload_encodes_unicode_metadata_before_sending_to_s3(monkeypatch):
    client = _RecordingS3Client()
    monkeypatch.setattr(s3_storage, "_init_s3", lambda: client)

    stored = s3_storage.upload_private_file(
        b"%PDF-1.7",
        category="contrats",
        extension="pdf",
        content_type="application/pdf",
        original_name="Contract maintenance preventive Salah Azaïz.pdf",
        content_hash="a" * 64,
        metadata={"uploaded-by": "José"},
    )

    assert stored is not None
    assert client.request is not None
    metadata = client.request["Metadata"]
    assert metadata["original-filename"] == "Contract%20maintenance%20preventive%20Salah%20Aza%C3%AFz.pdf"
    assert metadata["uploaded-by"] == "Jos%C3%A9"
    assert all(value.isascii() for value in metadata.values())


def test_s3_metadata_keys_and_values_are_encoded_to_ascii():
    metadata = s3_storage._ascii_metadata({"nom clé": "valeur à é"})

    assert metadata == {"nom%20cl%C3%A9": "valeur%20%C3%A0%20%C3%A9"}

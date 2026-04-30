"""
s3_storage.py — Module de stockage S3/MinIO pour SAVIA
=====================================================
Compatible avec:
  - MinIO (auto-hébergé, dev/staging)
  - AWS S3 (production)
  - Tout service S3-compatible (DigitalOcean Spaces, Backblaze B2, etc.)

Pour basculer de MinIO vers AWS S3 en production:
  1. Changer S3_ENDPOINT vers '' (vide = AWS par défaut)
  2. Mettre les credentials AWS dans S3_ACCESS_KEY / S3_SECRET_KEY
  3. Redéployer
"""

import os
import io
import hashlib
import logging
from datetime import datetime

logger = logging.getLogger("s3_storage")

# Configuration S3
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "savia-logs")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")

_client = None
S3_AVAILABLE = False


def _init_s3():
    """Initialise le client S3/MinIO."""
    global _client, S3_AVAILABLE
    if _client is not None:
        return _client

    if not S3_ACCESS_KEY or not S3_SECRET_KEY:
        logger.warning("⚠️ S3/MinIO non configuré (S3_ACCESS_KEY/S3_SECRET_KEY manquants)")
        return None

    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError

        kwargs = {
            "aws_access_key_id": S3_ACCESS_KEY,
            "aws_secret_access_key": S3_SECRET_KEY,
            "region_name": S3_REGION,
            "config": Config(
                signature_version='s3v4',
                retries={'max_attempts': 3, 'mode': 'adaptive'}
            ),
        }
        if S3_ENDPOINT:
            kwargs["endpoint_url"] = S3_ENDPOINT

        _client = boto3.client("s3", **kwargs)

        # Créer le bucket si nécessaire
        try:
            _client.head_bucket(Bucket=S3_BUCKET)
            logger.info(f"✅ S3 bucket '{S3_BUCKET}' accessible")
        except Exception:
            try:
                _client.create_bucket(Bucket=S3_BUCKET)
                logger.info(f"✅ S3 bucket '{S3_BUCKET}' créé avec succès")
            except Exception as e:
                logger.error(f"❌ Impossible de créer le bucket '{S3_BUCKET}': {e}")
                return None

        S3_AVAILABLE = True
        logger.info(f"✅ S3 Storage initialisé — Endpoint: {S3_ENDPOINT or 'AWS S3'}")
        return _client
    except ImportError:
        logger.error("❌ boto3 non installé. Installez-le avec: pip install boto3")
        return None
    except Exception as e:
        logger.error(f"❌ Erreur d'initialisation S3: {e}")
        return None


def upload_file(content: str, filename: str, equipement: str, metadata: dict = None) -> dict:
    """
    Upload un fichier log vers S3/MinIO.

    Args:
        content: Contenu textuel du fichier log
        filename: Nom du fichier original
        equipement: Nom de l'équipement associé
        metadata: Métadonnées supplémentaires (optionnel)

    Returns:
        dict avec 's3_key', 'content_hash', 'size_bytes' ou None si erreur
    """
    client = _init_s3()
    if not client:
        return None

    # Générer le hash SHA-256 pour l'intégrité
    content_bytes = content.encode('utf-8')
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    # Organiser par date et équipement: logs/2026/04/14/Giotto/filename.log
    now = datetime.utcnow()
    s3_key = f"logs/{now.strftime('%Y/%m/%d')}/{equipement}/{content_hash[:8]}_{filename}"

    # Métadonnées S3
    s3_metadata = {
        "equipement": equipement,
        "original-filename": filename,
        "content-hash-sha256": content_hash,
        "upload-timestamp": now.isoformat(),
    }
    if metadata:
        s3_metadata.update({k: str(v) for k, v in metadata.items()})

    try:
        client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content_bytes,
            ContentType="text/plain; charset=utf-8",
            Metadata=s3_metadata,
        )
        logger.info(f"✅ Log uploadé vers S3: {s3_key} ({len(content_bytes)} bytes)")
        return {
            "s3_key": s3_key,
            "content_hash": content_hash,
            "size_bytes": len(content_bytes),
        }
    except Exception as e:
        logger.error(f"❌ Upload S3 échoué: {e}")
        return None


def download_file(s3_key: str) -> str | None:
    """
    Télécharge un fichier log depuis S3/MinIO.

    Args:
        s3_key: Clé S3 du fichier

    Returns:
        Contenu texte du fichier ou None si erreur
    """
    client = _init_s3()
    if not client:
        return None

    try:
        response = client.get_object(Bucket=S3_BUCKET, Key=s3_key)
        content = response['Body'].read().decode('utf-8')
        return content
    except Exception as e:
        logger.error(f"❌ Download S3 échoué ({s3_key}): {e}")
        return None


def delete_file(s3_key: str) -> bool:
    """Supprime un fichier log de S3/MinIO."""
    client = _init_s3()
    if not client:
        return False

    try:
        client.delete_object(Bucket=S3_BUCKET, Key=s3_key)
        logger.info(f"🗑️ Fichier supprimé de S3: {s3_key}")
        return True
    except Exception as e:
        logger.error(f"❌ Suppression S3 échouée ({s3_key}): {e}")
        return False


def list_files(prefix: str = "logs/") -> list:
    """Liste les fichiers dans le bucket S3 avec un préfixe donné."""
    client = _init_s3()
    if not client:
        return []

    try:
        response = client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        files = []
        for obj in response.get('Contents', []):
            files.append({
                "key": obj['Key'],
                "size": obj['Size'],
                "last_modified": obj['LastModified'].isoformat(),
            })
        return files
    except Exception as e:
        logger.error(f"❌ Listing S3 échoué: {e}")
        return []

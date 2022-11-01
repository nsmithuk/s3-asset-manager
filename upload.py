#!/usr/bin/env python3

import base64
import glob
import hashlib
import logging
import os
from pathlib import Path

import boto3
import boto3.session
import colorama
from boto3 import Session
from botocore.credentials import RefreshableCredentials
from botocore.session import get_session
from colorama import Fore, Style

# -----------------------------------------------
# Function to get the S3 Client or Resource


def get_sts_session():
    def _refresh():
        params = {
            "RoleArn": os.environ['AWS_ROLE'],
            "DurationSeconds": 60 * 20,
            "RoleSessionName": "s3-asset-manager",
        }
        response = boto3.client('sts').assume_role(**params).get("Credentials")
        credentials = {
            "access_key": response.get("AccessKeyId"),
            "secret_key": response.get("SecretAccessKey"),
            "token": response.get("SessionToken"),
            "expiry_time": response.get("Expiration").isoformat(),
        }
        return credentials

    session_credentials = RefreshableCredentials.create_from_metadata(
        metadata=_refresh(),
        refresh_using=_refresh,
        method="sts-assume-role",
    )

    session = get_session()
    session._credentials = session_credentials
    autorefresh_session = Session(botocore_session=session)

    return autorefresh_session


def get_s3_client(logger):
    if 'AWS_ROLE' in os.environ:
        logger.info(f"Getting S3 client using assumed role: {os.environ['AWS_ROLE']}")
        return get_sts_session().client('s3')
    else:
        logger.info(f"Getting S3 client using credentials in environment variables")
        return boto3.client('s3')


def get_s3_resource(logger):
    if 'AWS_ROLE' in os.environ:
        logger.info(f"Getting S3 resource using assumed role: {os.environ['AWS_ROLE']}")
        return get_sts_session().resource('s3')
    else:
        logger.info(f"Getting S3 resource using credentials in environment variables")
        return boto3.resource('s3')


# --------------------------------
# Init

colorama.init(autoreset=True)

logging.basicConfig(format=Fore.YELLOW + '%(message)s', level=logging.INFO)
logger = logging.getLogger()

# --------------------------------
# Sense Check Inputs

package_dir = os.environ.get('PACKAGE_DIRECTORY')
if package_dir is None:
    logger.critical(Fore.RED + "Missing environment variable: PACKAGE_DIRECTORY")
    exit(100)

# --------------------------------
# Check if we already have the artifacts

if Path(package_dir + "/.found").is_file():
    logger.info(
        Fore.GREEN + "The artifact(s) for this commit already exist; skipping this step"
    )
    exit(0)

# --------------------------------
# Sense Check More Inputs

package_assets_bucket = os.environ.get('PACKAGE_ASSETS_BUCKET')
if package_assets_bucket is None:
    logger.critical(Fore.RED + "Missing environment variable: PACKAGE_ASSETS_BUCKET")
    exit(101)

# Returns all non-hidden files, directly in the package_dir
packages = [x for x in glob.glob(package_dir + "/*") if Path(x).is_file()]
if len(packages) < 1:
    logger.critical(Fore.RED + "No non-hidden files found in " + package_dir)
    exit(102)

if not Path(package_dir + "/.commit-hash").is_file():
    logger.critical(
        Fore.RED + "Commit Hash not found at " + package_dir + "/commit-hash"
    )
    exit(103)

# --------------------------------
# Get the hashes

commit_hash = open(package_dir + "/.commit-hash", "r").read()
logger.info("Commit hash: %s" % commit_hash)

code_hash = None
code_hash_dict = {}
if Path(package_dir + "/.code-hash").is_file():
    code_hash = open(package_dir + "/.code-hash", "r").read()
    code_hash_dict = {'code-hash': code_hash}
    logger.info("Code hash: %s" % code_hash)

# --------------------------------
# Upload the packages

s3_client = get_s3_client(logger)

text_colours = [Fore.BLUE, Fore.CYAN]

# Upload each of the packages
for idx, p in enumerate(packages):
    colour = idx % len(text_colours)

    path = Path(p)

    # Create the package hash, as expected by Lambda (base64 encoded SHA256)
    # For simplicity we do for this for all files, regardless of if they're lambda packages.
    package_hash = hashlib.sha256()
    with open(str(path), 'rb') as file:
        chunk = 0
        while chunk != b'':
            chunk = file.read(1024)
            package_hash.update(chunk)

    package_hash_encoded = str(base64.b64encode(package_hash.digest()), "utf-8")
    logger.info(
        text_colours[colour]
        + "Package hash for %s: %s"
        % (Style.BRIGHT + path.name + Style.NORMAL, package_hash_encoded)
    )

    key_artifact = "artifacts/%s/%s" % (commit_hash, path.name)
    logger.info(
        text_colours[colour]
        + "Uploading to s3://%s/%s" % (package_assets_bucket, key_artifact)
    )

    s3_client.upload_file(
        Filename=str(path),
        Bucket=package_assets_bucket,
        Key=key_artifact,
        ExtraArgs={
            'Metadata': {
                'commit-hash': commit_hash,
                'package-hash': package_hash_encoded,
                **code_hash_dict,
            }
        },
    )

    # ------

    if code_hash is not None:
        key_cache = "cache/%s/%s" % (code_hash, path.name)
        logger.info(
            text_colours[colour]
            + "Copying to s3://%s/%s" % (package_assets_bucket, key_cache)
        )

        s3_client.copy_object(
            CopySource={'Bucket': package_assets_bucket, 'Key': key_artifact},
            Bucket=package_assets_bucket,
            Key=key_cache,
            Metadata={
                'code-hash': code_hash,
                'commit-hash': commit_hash,
                'package-hash': package_hash_encoded,
            },
        )

logger.info(Fore.GREEN + "%s package(s) uploaded" % len(packages))

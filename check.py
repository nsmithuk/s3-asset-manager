#!/usr/bin/env python3

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
from colorama import Fore
from git import Repo

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

package_assets_bucket = os.environ.get('PACKAGE_ASSETS_BUCKET')
if package_assets_bucket is None:
    logger.critical(Fore.RED + "Missing environment variable: PACKAGE_ASSETS_BUCKET")
    exit(100)

git_repo_path = os.environ.get('GIT_REPO_PATH')
if git_repo_path is None:
    logger.critical(Fore.RED + "Missing environment variable: GIT_REPO_PATH")
    exit(101)

package_dir = os.environ.get('PACKAGE_DIRECTORY')
if package_dir is None:
    logger.critical(Fore.RED + "Missing environment variable: PACKAGE_DIRECTORY")
    exit(102)

# --------------------------------
# Get Git Commit Hash

repo = Repo(git_repo_path)

if repo.bare:
    logger.critical(Fore.RED + "Unable to load git repo")
    exit(103)

logger.info("Commit hash: %s" % repo.commit())
open(package_dir + "/.commit-hash", "w").write(str(repo.commit()))


# --------------------------------
# Check for artifact in the bucket

s3_client = get_s3_client(logger)

key_artifact = "artifacts/%s" % repo.commit()
logger.info(
    "Checking for artifacts at s3://%s/%s" % (package_assets_bucket, key_artifact)
)

object_list = s3_client.list_objects_v2(
    Bucket=package_assets_bucket, Prefix=key_artifact
)

if object_list['KeyCount'] > 0:
    Path(package_dir + "/.found").touch()
    logger.info(
        Fore.GREEN
        + "%d artifact(s) found; no build necessary" % object_list['KeyCount']
    )
    exit(0)

# --------------------------------
# Check for cache in the bucket

code_hash_find_filter = os.environ.get('CODE_HASH_FIND_FILTER')
if code_hash_find_filter is None:
    logger.info(
        Fore.YELLOW
        + "No packages found and no cache find filter set; new packages will need to be built"
    )
    exit(0)

logger.info("Artifact prefix not found; checking the cache")

filters = code_hash_find_filter.split(" ")

code_hash = hashlib.md5()
for pattern in filters:
    files = glob.glob("%s/%s" % (git_repo_path, pattern), recursive=True)
    files.sort()
    for f in files:
        if Path(f).is_file():
            with open(f, 'rb') as file:
                chunk = 0
                while chunk != b'':
                    chunk = file.read(1024)
                    code_hash.update(chunk)

hex_code_hash = code_hash.hexdigest()

logger.info("Code hash: %s" % hex_code_hash)
open(package_dir + "/.code-hash", "w").write(hex_code_hash)

key_cache = "cache/%s/" % hex_code_hash
logger.info(
    "Checking for cached packages at s3://%s/%s" % (package_assets_bucket, key_cache)
)

object_list = s3_client.list_objects_v2(Bucket=package_assets_bucket, Prefix=key_cache)

if object_list['KeyCount'] > 0:
    logger.info(Fore.GREEN + "%d cached artifact(s) found" % object_list['KeyCount'])

    text_colours = [Fore.BLUE, Fore.CYAN]

    s3_resource = get_s3_resource(logger)

    for idx, o in enumerate(object_list['Contents']):
        colour = idx % len(text_colours)

        obj = s3_resource.Object(package_assets_bucket, o['Key'])

        filename = obj.key.split('/')[-1]
        target_key = "%s/%s" % (key_artifact, filename)

        logger.info(text_colours[colour] + "Copying %s to %s" % (obj.key, target_key))

        s3_client.copy_object(
            CopySource={'Bucket': package_assets_bucket, 'Key': obj.key},
            Bucket=package_assets_bucket,
            Key=target_key,
            Metadata=obj.metadata,
        )

    Path(package_dir + "/.found").touch()
    logger.info(Fore.GREEN + "Artifact(s) copied from the cache; no build necessary")
    exit(0)

logger.info(Fore.YELLOW + "No package found; a new one will need to be built")

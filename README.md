# S3 Asset Manager

A tool for checking if assets for a given git commit exist in an S3 bucket and, if not, uploading
the (externally) generated assets once they have been created.

This is designed to be run in a CI/CD pipeline, using a Docker container, built from [Dockerfile](Dockerfile).

## Parameters

### Required for 'check' and 'upload'
- **PACKAGE_ASSETS_BUCKET**: The name of the S3 bucket in which to store the assets.

### Optional for 'check'
- **GIT_REPO_PATH**: The path at which the script will find the root of the git repository. *Defaults to ./repo*
- **CODE_HASH_FIND_FILTER**: Setting this enabled caching. 
Takes a [Unix style pathname pattern expansion](https://docs.python.org/3/library/glob.html) to determine what 
files to include in the code hash (see caching below). *Defaults to None / Disabled*

### Optional for 'check' and 'upload'
- **PACKAGE_DIRECTORY**: The directory in which the scripts will store metadata, and check for assets to be uploaded. 
The contents of this path must persist between pipeline tasks. *Defaults to ./packages*

## Using in Concourse

The check stage, to be run first:
```yaml
    - task: check-for-packages
      params:
        GIT_REPO_PATH: "./repo-name"
        CODE_HASH_FIND_FILTER: "lambdas/**"
        PACKAGE_ASSETS_BUCKET: "bucket-name"
        <<: *aws_creds
      config:
        platform: linux
        image_resource:
          type: docker-image
          source:
            repository: ghcr.io/nsmithuk/s3-asset-manager       
        inputs:
          - name: repo        
        outputs:
          - name: packages        
        run:
          path: check
```

The upload stage, to be run last:
```yaml
    - task: upload-packages
      params:
        PACKAGE_ASSETS_BUCKET: "bucket-name"
        <<: *aws_creds
      config:
        platform: linux
        image_resource:
          type: docker-image
          source:
            repository: ghcr.io/nsmithuk/s3-asset-manager       
        inputs:
          - name: packages        
        run:
          path: upload
```

## How it works

### check

Check first determines the commit hash of the git repository. It expects the root of the git repository to be
found at the path defined by `GIT_REPO_PATH`.

It then checks in the S3 bucket, defined by `PACKAGE_ASSETS_BUCKET`, for if there are _any_ objects with the key prefix
`artifacts/<commit-hash>`.

#### If found...
Then check assume the assets have already been built and uploaded.
It flags this by touching the path `$PACKAGE_DIRECTORY/.found`.

#### If not found...
Then check assumes that either:
- The assets need building and uploading; or
- If caching is enabled, we can copy the assets out of the cache (see caching below).

#### Either way...
After check finishes running, if the file `$PACKAGE_DIRECTORY/.found` does not exist, following tasks should
assume they need to build and upload the assets.

### upload

First upload checks if the file `$PACKAGE_DIRECTORY/.found` exists. If so it assumes it has nothing to do and exits.

Otherwise it uploads all the (non-hidden) files found in `$PACKAGE_DIRECTORY/` into S3, 
under the key prefix `artifacts/<commit-hash>/`.

If caching is enabled, a copy of the assets are also stored under the path `cache/<code-hash>`.

## Caching

... to write.

## Local Usage (for testing)

To run a check:
```shell
docker run -it --rm \
-e AWS_ACCESS_KEY_ID \
-e AWS_SECRET_ACCESS_KEY \
-e AWS_SESSION_TOKEN \
-e AWS_DEFAULT_REGION="eu-west-2" \
-e PACKAGE_ASSETS_BUCKET="test-bucket-name" \
-v "${PWD}:/app" \
-v "${PWD}/local-repo:/repo" \
-w "/app" \
ghcr.io/nsmithuk/s3-asset-manager:latest check
```

To run an upload:
```shell
docker run -it --rm \
-e AWS_ACCESS_KEY_ID \
-e AWS_SECRET_ACCESS_KEY \
-e AWS_SESSION_TOKEN \
-e AWS_DEFAULT_REGION="eu-west-2" \
-e PACKAGE_ASSETS_BUCKET="test-bucket-name" \
-v "${PWD}:/app" \
-v "${PWD}/local-repo:/repo" \
-w "/app" \
ghcr.io/nsmithuk/s3-asset-manager:latest upload
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

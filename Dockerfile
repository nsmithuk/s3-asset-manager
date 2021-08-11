FROM python:3-alpine

RUN apk add --update --no-cache git

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY check.py /usr/local/bin/check
RUN chmod a+x /usr/local/bin/check

COPY upload.py /usr/local/bin/upload
RUN chmod a+x /usr/local/bin/upload

ENV GIT_REPO_PATH="./repo"
ENV PACKAGE_DIRECTORY="./packages"

CMD ["sh"]

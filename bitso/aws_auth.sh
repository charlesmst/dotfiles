#!/bin/bash
set -e
credential_id=5qhokpk6biwq7obiqvovufac24
export SAML2AWS_ROLE=$1
export SAML2AWS_USERNAME=$(op item get $credential_id --fields username)
export SAML2AWS_PASSWORD=$(op item get  $credential_id --fields password)
export SAML2AWS_MFA_TOKEN=$(op item get --totp $credential_id )
saml2aws login  --skip-prompt --quiet --credential-process

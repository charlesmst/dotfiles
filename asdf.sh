#!/bin/bash

DEFAULT_NODE_VERSION=16.16.0

asdf plugin-add kubectl https://github.com/Banno/asdf-kubectl.git || true
asdf plugin-add helm https://github.com/Antiarchitect/asdf-helm.git || true
asdf plugin-add nodejs https://github.com/asdf-vm/asdf-nodejs.git || true
asdf plugin-add packer https://github.com/Banno/asdf-hashicorp.git || true
asdf plugin-add terraform https://github.com/Banno/asdf-hashicorp.git || true
asdf plugin-add vault https://github.com/Banno/asdf-hashicorp.git || true
asdf plugin-add tflint https://github.com/skyzyx/asdf-tflint || true
asdf plugin-add golang https://github.com/kennyp/asdf-golang.git || true


asdf install kubectl latest 1.15.0 1.17.0
asdf install helm latest 2.14.3
asdf install packer latest 1.3.3
asdf install terraform latest 0.11.11 0.12.21 0.13.6 0.14.7 0.15.1 1.0.0
asdf install vault latest 1.3.2
asdf install nodejs $DEFAULT_NODE_VERSION
asdf install tflint 0.23.1
asdf install golang 1.17.1

asdf global kubectl 1.17.0
asdf global helm 2.14.3
asdf global nodejs $DEFAULT_NODE_VERSION
asdf global packer 1.3.3
asdf global terraform 1.0.0
asdf global vault 1.3.2
asdf global tflint 0.23.1
asdf global golang 1.17.1


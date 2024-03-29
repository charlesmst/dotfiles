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
asdf plugin-add java https://github.com/halcyon/asdf-java.git || true
asdf plugin-add rust https://github.com/code-lever/asdf-rust.git || true
asdf plugin-add redis https://github.com/smashedtoatoms/asdf-redis.git || true

asdf install kubectl 1.24.3
asdf install helm latest 2.14.3
asdf install packer latest 1.3.3
asdf install terraform latest 0.11.11 0.12.21 0.13.6 0.14.7 0.15.1 1.0.0
asdf install vault latest 1.10.4
asdf install nodejs $DEFAULT_NODE_VERSION
asdf install tflint 0.23.1
asdf install golang 1.18.3
asdf install java openjdk-17.0.2
asdf install rust 1.63.0
asdf install redis 7.0.8

asdf global kubectl 1.24.3
asdf global helm 2.14.3
asdf global nodejs $DEFAULT_NODE_VERSION
asdf global packer 1.3.3
asdf global terraform 1.0.0
asdf global vault 1.10.4
asdf global tflint 0.23.1
asdf global golang 1.18.3
asdf global java openjdk-17.0.2
asdf global rust 1.63.0
asdf global redis 7.0.8

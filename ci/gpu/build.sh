#!/bin/bash

#
# Copyright 2020 NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

################################################################################
# VariantWorks CPU/GPU conda build script for CI
################################################################################

set -e

START_TIME=$(date +%s)

export PATH=/conda/bin:/usr/local/cuda/bin:$PATH
# Set home to the job's workspace
export HOME=$WORKSPACE
cd "${WORKSPACE}"

################################################################################
# Init
################################################################################

source ci/utilities/logger.sh

logger "Calling prep-init-env..."
source ci/utilities/prepare_env.sh

################################################################################
# VariantWorks tests
################################################################################

logger "Build VariantWorks..."
cd "${WORKSPACE}"
source ci/utilities/test_variantworks.sh

logger "Done..."

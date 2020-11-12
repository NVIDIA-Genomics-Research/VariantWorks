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

import os
import pytest
import shutil

import nemo
from nemo.backends.pytorch.common.losses import CrossEntropyLossNM
from nemo.backends.pytorch.torchvision.helpers import eval_epochs_done_callback, eval_iter_callback
import torch

from variantworks.dataloader import VariantDataLoader
from variantworks.io.vcfio import VCFReader
from variantworks.networks import AlexNet
from variantworks.encoders import ZygosityLabelDecoder

from test_utils import get_data_folder


@pytest.mark.gpu
def test_simple_vc_trainer():
    # Train a sample model with test data

    # Create neural factory
    model_dir = os.path.join(get_data_folder(), ".test_model")
    nf = nemo.core.NeuralModuleFactory(
        placement=nemo.core.neural_factory.DeviceType.GPU, checkpoint_dir=model_dir
    )

    # Generate dataset
    bam = os.path.join(get_data_folder(), "small_bam.bam")
    labels = os.path.join(get_data_folder(), "candidates.vcf.gz")
    vcf_loader = VCFReader(vcf=labels, bams=[bam], is_fp=False)

    # Neural Network
    alexnet = AlexNet(num_input_channels=1, num_output_logits=3)

    # Create train DAG
    dataset_train = VariantDataLoader(VariantDataLoader.Type.TRAIN, [vcf_loader],
                                      batch_size=32, shuffle=True)
    vz_ce_loss = CrossEntropyLossNM(logits_ndim=2)
    encoding, vz_labels = dataset_train()
    vz = alexnet(encoding=encoding)
    vz_loss = vz_ce_loss(logits=vz, labels=vz_labels)

    # Create evaluation DAG using same dataset as training
    dataset_eval = VariantDataLoader(VariantDataLoader.Type.EVAL, [vcf_loader],
                                     batch_size=32, shuffle=False)
    vz_ce_loss_eval = CrossEntropyLossNM(logits_ndim=2)
    encoding_eval, vz_labels_eval = dataset_eval()
    vz_eval = alexnet(encoding=encoding_eval)
    vz_loss_eval = vz_ce_loss_eval(logits=vz_eval, labels=vz_labels_eval)

    # Logger callback
    logger_callback = nemo.core.SimpleLossLoggerCallback(
        tensors=[vz_loss, vz, vz_labels],
        step_freq=1,
    )

    evaluator_callback = nemo.core.EvaluatorCallback(
        eval_tensors=[vz_loss_eval, vz_eval, vz_labels_eval],
        user_iter_callback=eval_iter_callback,
        user_epochs_done_callback=eval_epochs_done_callback,
        eval_step=1,
    )

    # Checkpointing models through NeMo callback
    checkpoint_callback = nemo.core.CheckpointCallback(
        folder=nf.checkpoint_dir,
        load_from_folder=None,
        # Checkpointing frequency in steps
        step_freq=-1,
        # Checkpointing frequency in epochs
        epoch_freq=1,
        # Number of checkpoints to keep
        checkpoints_to_keep=1,
        # If True, CheckpointCallback will raise an Error if restoring fails
        force_load=False
    )

    # Invoke the "train" action.
    nf.train([vz_loss],
             callbacks=[logger_callback,
                        checkpoint_callback, evaluator_callback],
             optimization_params={"num_epochs": 1, "lr": 0.001},
             optimizer="adam")

    assert(os.path.exists(os.path.join(model_dir, "AlexNet-EPOCH-1.pt")))


@pytest.mark.gpu
@pytest.mark.depends(on=['test_simple_vc_trainer'])
def test_simple_vc_infer():
    # Load checkpointed model and run inference
    test_data_dir = get_data_folder()
    model_dir = os.path.join(test_data_dir, ".test_model")

    # Create neural factory
    nf = nemo.core.NeuralModuleFactory(
        placement=nemo.core.neural_factory.DeviceType.GPU, checkpoint_dir=model_dir
    )

    # Generate dataset
    bam = os.path.join(test_data_dir, "small_bam.bam")
    labels = os.path.join(test_data_dir, "candidates.vcf.gz")
    vcf_loader = VCFReader(vcf=labels, bams=[bam], is_fp=False)
    test_dataset = VariantDataLoader(VariantDataLoader.Type.TEST, [vcf_loader], batch_size=32,
                                     shuffle=False)

    # Neural Network
    alexnet = AlexNet(num_input_channels=1, num_output_logits=3)

    # Create train DAG
    encoding = test_dataset()
    vz = alexnet(encoding=encoding)

    # Invoke the "train" action.
    results = nf.infer([vz], checkpoint_dir=model_dir, verbose=True)

    # Decode inference results to labels
    zyg_decoder = ZygosityLabelDecoder()
    for tensor_batches in results:
        for batch in tensor_batches:
            predicted_classes = torch.argmax(batch, dim=1)
            inferred_zygosity = [zyg_decoder(pred)
                                 for pred in predicted_classes]

    assert(len(inferred_zygosity) == len(vcf_loader))

    shutil.rmtree(model_dir)

#!/usr/bin/env python

import argparse
import datetime
import json
import socket
import sys
import time
from pathlib import Path

import numpy as np
import tensorflow as tf
from Modules import models, tf_utils, utils
from Modules.tf_utils import correlate, mae_cor
from tensorflow.keras.callbacks import (
    CSVLogger,
    EarlyStopping,
    ModelCheckpoint,
    ReduceLROnPlateau,
)
from tensorflow.keras.optimizers import Adam


def parsing():
    """
    Parse the command-line arguments.

    Arguments
    ---------
    python command-line
    """
    # Declaration of expexted arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-arch",
        "--architecture",
        help='Name of the model architecture in "models.py". '
        'If you wish to use your own, you will need to add it to "models.py" '
        'and also to the dictionary "model_dict" in this script.',
        type=str,
        required=True,
    )
    parser.add_argument(
        "-g",
        "--genome",
        help="One-hot encoded genome file in npz archive, with one array per "
        "chromosome",
        type=str,
        required=True,
    )
    parser.add_argument(
        "-l",
        "--labels",
        help="Label file in npz archive, with one array per chromosome",
        type=str,
        required=True,
    )
    parser.add_argument(
        "-out",
        "--output",
        help="Path to the output directory. If it doesn't exist, it will be created. "
        "However it should be empty otherwise files in it may be overwritten.",
        type=str,
        required=True,
    )
    parser.add_argument(
        "-ct",
        "--chrom_train",
        help="Chromosomes to use for training",
        nargs="+",
        type=str,
        required=True,
    )
    parser.add_argument(
        "-cv",
        "--chrom_valid",
        help="Chromosomes to use for validation",
        nargs="+",
        type=str,
        required=True,
    )
    parser.add_argument(
        "-s",
        "--strand",
        help="Strand to perform training on, choose between 'for', 'rev' or "
        "'both' (default: %(default)s)",
        type=str,
        default="both",
    )
    parser.add_argument(
        "-w",
        "--winsize",
        help="Size of the window in bp to use for prediction (default: %(default)s)",
        default=2001,
        type=int,
    )
    parser.add_argument(
        "-h_int",
        "--head_interval",
        help="Spacing between output head in case of mutliple outputs. "
        "If not set, consider a single output in the middle of the window (default: %(default)s)",
        default=None,
        type=int,
    )
    parser.add_argument(
        "-lr",
        "--learn_rate",
        help="Value for learning rate (default: %(default)s)",
        default=0.001,
        type=float,
    )
    parser.add_argument(
        "-ep",
        "--epochs",
        help="Number of training loops over the entire sample data (default: %(default)s)",
        default=100,
        type=int,
    )
    parser.add_argument(
        "-b",
        "--batch_size",
        help="Number of samples to use per training step (default: %(default)s)",
        default=1024,
        type=int,
    )
    parser.add_argument(
        "-ss",
        "--same_samples",
        help="Indicates to use the same sample at each epoch. Otherwise, "
        "change the sample by first fetching data that hasn't been used "
        "in the previous epochs.",
        action="store_true",
    )
    parser.add_argument(
        "-mt",
        "--max_train",
        help="Maximum number of windows per epoch for training (default: %(default)s)",
        default=2**22,
        type=int,
    )
    parser.add_argument(
        "-mv",
        "--max_valid",
        help="Maximum number of windows per epoch for validation (default: %(default)s)",
        default=2**20,
        type=int,
    )
    parser.add_argument(
        "-bal",
        "--balance",
        help="'global' indicates to balance sample weights globally and 'batch' "
        "indicates to balance sample weights in each batch. If not set, no weights "
        "are used (default: %(default)s)",
        default=None,
        type=str,
    )
    parser.add_argument(
        "-nc",
        "--n_classes",
        help="Number of bins to divide values into for sample weighting (default: %(default)s)",
        default=500,
        type=int,
    )
    parser.add_argument(
        "-r0",
        "--remove0s",
        action="store_true",
        help="Indicates to remove 0 labels from training set. "
        "Recommended to avoid training on non-mappable regions",
    )
    parser.add_argument(
        "-rN",
        "--removeNs",
        action="store_true",
        help="Indicates to remove windows with N from training set. In the one-hot "
        "encoding format, this corresponds to a vector of all 0s",
    )
    parser.add_argument(
        "-r",
        "--remove_indices",
        help="Npz file containing indices of labels to remove from "
        "training set, with one array per chromosome",
        default=None,
        type=str,
    )
    parser.add_argument(
        "--seed",
        help="Seed to use for random operations, which include model weights "
        "initialization and training samples shuffling",
        default=None,
        type=int,
    )
    parser.add_argument(
        "-da",
        "--disable_autotune",
        action="store_true",
        help="Indicates not to use earlystopping.",
    )
    parser.add_argument(
        "-p",
        "--patience",
        help="Patience parameter for earlystopping: number of epochs "
        "without improvement on the validation set to wait before stopping "
        "training (default: %(default)s)",
        default=6,
        type=int,
    )
    parser.add_argument(
        "-dist",
        "--distribute",
        action="store_true",
        help="Indicates to use multiple GPUs with MirrorStrategy.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="0 for silent, 1 for progress bar and 2 for single line (default: %(default)s)",
        default=2,
        type=int,
    )
    args = parser.parse_args()
    # Check if the input data is valid
    if not Path(args.genome).is_file():
        sys.exit(
            f"{args.genome} does not exist.\n" "Please enter a valid genome file path."
        )
    if not Path(args.labels).is_file():
        sys.exit(
            f"{args.labels} does not exist.\n" "Please enter a valid labels file path."
        )
    genome_name = Path(args.genome).stem
    if genome_name == "W303":
        args.chrom_train = ["chr" + format(int(c), "02d") for c in args.chrom_train]
        args.chrom_valid = ["chr" + format(int(c), "02d") for c in args.chrom_valid]
    elif genome_name == "W303_Mmmyco":
        args.chrom_train = [f"chr{c}" if c != "Mmmyco" else c for c in args.chrom_train]
        args.chrom_valid = [f"chr{c}" if c != "Mmmyco" else c for c in args.chrom_valid]
    with np.load(args.genome) as g:
        with np.load(args.labels) as s:
            for chr_id in args.chrom_train + args.chrom_valid:
                if not (chr_id in g.keys() and chr_id in s.keys()):
                    sys.exit(
                        f"{chr_id} is not a valid chromosome id in "
                        f"{args.genome} and {args.labels}"
                    )
    if args.remove_indices is not None:
        with np.load(args.remove_indices) as r:
            for chr_id in args.chrom_train + args.chrom_valid:
                if chr_id not in r.keys():
                    sys.exit(
                        f"{chr_id} is not a valid chromosome id in "
                        f"{args.remove_indices}"
                    )
    return args


if __name__ == "__main__":
    tmstmp = datetime.datetime.now()
    # Get arguments
    args = parsing()
    # Maybe build output directory
    Path(args.output).mkdir(parents=True, exist_ok=True)
    # Store arguments in file
    with open(Path(args.output, "Experiment_info.txt"), "w") as f:
        json.dump(vars(args), f, indent=4)
        f.write("\n")
        f.write(f"timestamp: {tmstmp}\n")
        f.write(f"machine: {socket.gethostname()}\n")

    # Limit gpu memory usage
    tf.debugging.set_log_device_placement(True)
    gpus = tf.config.list_physical_devices("GPU")
    if gpus:
        try:
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
        except RuntimeError as e:
            print(e)

    # Set random seed for tensorflow model initialisation
    if args.seed is not None:
        tf.random.set_seed(args.seed)
    # Build model with chosen strategy
    model_dict = {
        "mnase_Etienne": models.mnase_Etienne,
        "bassenji_Etienne": models.bassenji_Etienne,
    }
    model_builder = model_dict[args.architecture]
    if args.distribute:
        strategy = tf.distribute.MirroredStrategy()
        with strategy.scope():
            model = model_builder(winsize=args.winsize)
            model.compile(
                optimizer=Adam(learning_rate=args.learn_rate),
                loss=mae_cor,
                metrics=["mae", correlate],
            )
    else:
        model = model_builder(winsize=args.winsize)
        model.compile(
            optimizer=Adam(learning_rate=args.learn_rate),
            loss=mae_cor,
            metrics=["mae", correlate],
        )

    # Load the data
    x_train = utils.merge_chroms(args.chrom_train, args.genome)
    x_valid = utils.merge_chroms(args.chrom_valid, args.genome)
    y_train = utils.merge_chroms(args.chrom_train, args.labels)
    y_valid = utils.merge_chroms(args.chrom_valid, args.labels)
    if args.remove_indices is not None:
        with np.load(args.remove_indices) as f:
            with np.load(args.labels) as s:
                remove_indices_train, remove_indices_valid = [], []
                total_len_train, total_len_valid = 0, 0
                for k in args.chrom_train:
                    remove_indices_train.append(f[k] + total_len_train)
                    total_len_train += len(s[k]) + 1
                remove_indices_train = np.concatenate(remove_indices_train)
                for k in args.chrom_valid:
                    remove_indices_valid.append(f[k] + total_len_valid)
                    total_len_valid += len(s[k]) + 1
                remove_indices_valid = np.concatenate(remove_indices_valid)
    else:
        remove_indices_train = None
        remove_indices_valid = None
    # Build generators
    generator_train = tf_utils.WindowGenerator(
        data=x_train,
        labels=y_train,
        winsize=args.winsize,
        batch_size=args.batch_size,
        max_data=args.max_train,
        same_samples=args.same_samples,
        balance=args.balance,
        n_classes=args.n_classes,
        strand=args.strand,
        head_interval=args.head_interval,
        remove0s=args.remove0s,
        removeNs=args.removeNs,
        remove_indices=remove_indices_train,
        seed=args.seed,
    )
    generator_valid = tf_utils.WindowGenerator(
        data=x_valid,
        labels=y_valid,
        winsize=args.winsize,
        batch_size=args.batch_size,
        max_data=args.max_valid,
        same_samples=True,
        strand=args.strand,
        head_interval=args.head_interval,
        remove0s=args.remove0s,
        removeNs=args.removeNs,
        remove_indices=remove_indices_valid,
        seed=0,
    )
    # Create callbacks during training
    callbacks_list = [CSVLogger(Path(args.output, "epoch_data.csv"))]
    # Add optional autotune callbakcs
    if not args.disable_autotune:
        callbacks_list.append(
            [
                ModelCheckpoint(
                    filepath=Path(args.output, "Checkpoint"),
                    monitor="val_correlate",
                    save_best_only=True,
                ),
                EarlyStopping(
                    monitor="val_loss",
                    patience=args.patience,
                    min_delta=1e-4,
                    restore_best_weights=True,
                ),
                ReduceLROnPlateau(
                    monitor="val_loss",
                    factor=0.1,
                    patience=args.patience // 2,
                    min_lr=0.1 * args.learn_rate,
                ),
            ]
        )
    # Train model
    t0 = time.time()
    model.fit(
        generator_train,
        validation_data=generator_valid,
        epochs=args.epochs,
        callbacks=callbacks_list,
        verbose=args.verbose,
        shuffle=False,
    )
    train_time = time.time() - t0
    with open(Path(args.output, "Experiment_info.txt"), "a") as f:
        f.write(f"training time: {train_time}\n")
    # Save trained model
    model.save(Path(args.output, "model"))

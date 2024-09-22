# bacterial_genome

___________________________________________________________________
### General description
This repository can be used to predict the nucleosome, cohesine and polymerase coverage on bacterial genome introduced in _Saccharomyces cerevisiae_.

The two main scripts are `Train_profile.py` and `predict_profile.py`. `Train_profile.py` can be used to train a model from genome and labels. `predict_profile.py` can be used to perform predictions on a genome given a trained model. Genome and labels are expected as numpy binary files, genomes being already one-hot encoded. The helper scripts `one_hot_encode.py`, `bw_to_npz.py` and `npz_to_bw.py` can be used to convert between the different file formats.

______________________________________________________________________
### Models availability
The models trained on _Saccharomyces cerevisiae_ to predict the nucleosome, polymerase and cohesine coverage are available in Trainedmodels.

___________________________________________________________________________
### Data availability
The bacterial genomes are available in genome, both as fasta files and in one-hot encoded format in numpy binary files.
The labels used to train the models are available in data, in numpy binary files.

________________________________________________________________________

### Code reproducibility
Two environment files are provided: `tf2.5cpu.yml` and `tf2.5gpu.yml`. The second is simply an extension of the first allowing gpu acceleration, through cudatoolkit and cudnn. This can be hardware dependent, so the tf2.5cpu environment is also provided. You will still be able to run the code, but it will be much slower on cpu. You may also install your own packages on top of it to allow gpu acceleration.
In a nutshell, these environments have python3.8 with tensorflow2.5, numpy and pyBigWig.

The file `bash_commands.sh` shows commands used to train models and make predictions. The predictions aren't provided but running the prediction commands should provide the same results.

The two scripts `Yeast_MNase_pipeline.py` and `Yeast_ChIP_pipeline.py` were used to transform the MNase and ChIP files into the label files provided in data. These are provided as information, not necessarily to be rerun. If you wish to do so, you will need to download data from GSE217022. If you wish to apply them on your own data, you will probably need to adapt parts of the code (for example the remove_artifacts function).

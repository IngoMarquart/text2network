# TODO: Comment
import logging
class configuration:
    """
    Simple class to store our options
    """
    #%% Analysis options:
    years=range(1990,2020)
    prune_min=0.025
    cluster_windows=[2,3]
    ego_radius=1
    num_retain=250
    num_retain_cluster=250
    cluster_levels=4
    cluster_levels_overall = 6
    save_cluster_to_xlsx = True
    #%% Plot options:
    focal_nodes=["leader","leadership",'manager','management']
    ego_limit=20

    #%% Folders:
    model_dir = "D:/NLP/BERT-NLP/NLP/models"
    data_folder = "D:/NLP/ESMTNLP/BERTNLP/data"
    input_folder = "D:/NLP/ESMTNLP/BERTNLP/text"
    text_folder = 'D:/NLP/ESMTNLP/BERTNLP/data/text'
    nw_folder="/networks"
    plot_folder = ''.join([data_folder,'/plots/'])

    #%% Logging
    subprocess_level=logging.INFO


    #%% Text Preprocessing options
    max_seq_length = 30
    char_mult=10
    max_seq=0

    #%% BERT Training options
    gpu_batch=100
    epochs=200
    loss_limit=0.5
    warmup_steps = 0
    mlm_probability = 0.15
    do_train=True

    #%% BERT Inference Options
    batch_size=30


    #%% Network creation options
    cutoff_percent = 95
    max_degree=30
    plural_method="sum"

    #%% Moving Average options
    ma_order=3
    average_links=True

# %% Imports

import glob
import logging
import os
import time

import networkx as nx
import torch

from NLP.config.config import configuration
from NLP.src.neo4j.process_sentences_neo4j import process_sentences_neo4j
from NLP.src.run_bert import bert_args, run_bert
from NLP.src.text_processing.preprocess_files_HBR import preprocess_files_HBR
from NLP.utils.hash_file import hash_file, check_step, complete_step
from NLP.utils.load_bert import get_bert_and_tokenizer

# %% Config
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(name)s -   %(message)s',
                    datefmt='%m/%d/%Y %H:%M:%S',
                    level=logging.INFO)
cfg = configuration()


if __name__ == "__main__":
    # %% Main Loop:
    years = [2000]
    for year in years:
        logging.info("---------- Starting year %i ----------" % year)
        input_folder = 'D:/NLP/BERT-NLP/NLP/data/HBR/articles/'
        input_folder = ''.join([input_folder, str(year)])

        # %% Create folder structure
        logging.info("Setting up folder structure")
        text_folder = ''.join([cfg.text_folder, '/', str(year)])
        data_folder = ''.join([cfg.data_folder, '/', str(year)])
        bert_folder = ''.join([data_folder, '/bert'])
        tensor_folder = ''.join([data_folder, '/tensors'])
        nw_folder = ''.join([data_folder, cfg.nw_folder])
        sum_folder = ''.join([data_folder, cfg.sums_folder])
        np_folder = ''.join([data_folder, cfg.np_folder])
        ma_folder = ''.join([data_folder, cfg.ma_folder])
        entropy_folder = ''.join([data_folder, cfg.entropy_folder])
        sumsym_folder = ''.join([data_folder, cfg.sumsym_folder])
        text_file = ''.join([text_folder, '/', str(year), '.txt'])
        text_db = ''.join([text_folder, '/', str(year), '.h5'])
        plot_folder = ''.join([cfg.data_folder, '/plots'])

        if not os.path.exists(text_folder): os.mkdir(text_folder)
        if not os.path.exists(data_folder): os.mkdir(data_folder)
        if not os.path.exists(bert_folder): os.mkdir(bert_folder)
        if not os.path.exists(tensor_folder): os.mkdir(tensor_folder)
        if not os.path.exists(nw_folder): os.mkdir(nw_folder)
        if not os.path.exists(sum_folder): os.mkdir(sum_folder)
        if not os.path.exists(np_folder): os.mkdir(np_folder)
        if not os.path.exists(plot_folder): os.mkdir(plot_folder)
        if not os.path.exists(ma_folder): os.mkdir(ma_folder)
        if not os.path.exists(entropy_folder): os.mkdir(entropy_folder)
        if not os.path.exists(sumsym_folder): os.mkdir(sumsym_folder)

        logging.info("Copying separate text files into text folder.")
        read_files = glob.glob(''.join([input_folder, '/*.txt']))

        with open(text_file, "wb") as outfile:
            for f in read_files:
                with open(f, "rb") as infile:
                    outfile.write(infile.read())

        # %% Get file hash
        hash = hash_file(text_file, hash_factory="md5")
        logging.info("File Hash is %s" % hash)

        # %% Preprocess files
        logging.info("Pre-processing text file")
        if check_step(text_folder, hash):
            logging.info("Pre-processing already completed, skipping")
        else:
            start_time = time.time()
            logging.disable(cfg.subprocess_level)
            preprocess_files_HBR(input_folder, text_db, cfg.max_seq_length, cfg.char_mult, max_seq=cfg.max_seq)
            logging.disable(logging.NOTSET)
            logging.info("Pre-processing finished in %s seconds" % (time.time() - start_time))
            complete_step(text_folder, hash)

        # %% Train BERT
        logging.info("Training BERT")
        if (check_step(bert_folder, hash)):
            logging.info("Found trained BERT. Skipping")
        else:

            start_time = time.time()
            # Create BERT args
            args = bert_args(text_file, bert_folder, cfg.do_train, cfg.model_dir, cfg.mlm_probability, cfg.max_seq_length,
                             cfg.loss_limit, cfg.gpu_batch, cfg.epochs,
                             cfg.warmup_steps)
            torch.cuda.empty_cache()
            logging.disable(cfg.subprocess_level)
            results = run_bert(args)
            logging.disable(logging.NOTSET)
            logging.info("BERT results %s" % results)
            logging.info("BERT training finished in %s seconds" % (time.time() - start_time))
            complete_step(bert_folder, hash)

        # %% Process files, create networks

        logging.info("Processing text to create networks.")
        if (check_step(nw_folder, hash)):
            logging.info("Processed results found. Skipping.")
        else:
            start_time = time.time()
            torch.cuda.empty_cache()
            logging.disable(cfg.subprocess_level)
            tokenizer, bert = get_bert_and_tokenizer(bert_folder, True)
            logging.disable(logging.NOTSET)
            DICT_SIZE = tokenizer.vocab_size
            # Process sentences in BERT and create the networks
            process_sentences_neo4j(tokenizer, bert, text_db, cfg.max_seq_length,
                                                                              DICT_SIZE,
                                                                              cfg.batch_size,
                                                                              nr_workers=0,
                                                                              cutoff_percent=cfg.cutoff_percent,
                                                                              max_degree=cfg.max_degree)
"""# Dependency install

!pip install datasets
!pip install -q -U google-generativeai

# Imports
"""

import re
import os
import time
import nltk
import wandb
import torch
import random
import numpy as np
import pandas as pd
import torch.nn as nn
from tqdm import tqdm
from torch.utils import data
from collections import Counter
from google.api_core import retry
from torch.nn import functional as F
import google.generativeai as gemini_ai
from transformers import GPT2TokenizerFast
from transformers import BitsAndBytesConfig
from kaggle_secrets import UserSecretsClient
from google.generativeai.types import RequestOptions
from datasets import load_dataset, Dataset, DatasetDict
from torch.nn import TransformerDecoder, TransformerEncoder
from torch.nn import TransformerEncoderLayer, TransformerDecoderLayer
# from peft import prepare_model_for_kbit_training, LoraConfig, get_peft_model
from transformers import AutoTokenizer, AutoModelForCausalLM, PreTrainedTokenizerFast
from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, decoders, trainers

"""# Setup

## API Keys
"""

user_secrets = UserSecretsClient()

"""### Wandb"""

wandb_api_key = user_secrets.get_secret("WANDB_API_KEY")

wandb.login(key=wandb_api_key)

"""### Gemini"""

gemini_api_key = user_secrets.get_secret("GEMINI_API_KEY")

gemini_ai.configure(api_key=gemini_api_key)

"""## Running on GPU (if available)"""

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

"""# Config

## Config for Hyperparameters
"""

config = {
    "BLOCK_SIZE": 128,
    "EMB_SIZE": 558,
    "N_ATTENTION_HEADS": 18,
    "N_ENCODER_BLOCKS": 1,
    "N_DECODER_BLOCKS": 1,
    "DIM_FEEDFORWRD": 4096,
    "LSTM_LAYERS": 2,
    "VOCAB_SIZE": 10000,
    "DROPOUT": 0.1,
    "MAX_LENGTH": 512,
    "MAX_OUT_TOKENS": 200,
    "EVAL_ITER": 100,
    "LR": 3e-4,
    "BATCH_SIZE": 32,
    "EPOCHS": 1,
    "PATIENCE": 3,
    "MODEL_NAME": "custom-21",
    "WORKING_DIR": "/kaggle/working",
    "VOCAB_DIRNAME": "/kaggle/input/vocab-dict-v2/vocab_dict_v2",
    "DF_PATH": "/kaggle/input/compare-dataframes/rating_df_baseline-21.pkl",
    "LOAD_MODELPATH": "/kaggle/input/custom-v2/pytorch/default/1/custom-21_good.pt",
    "DEVICE": 'cuda' if torch.cuda.is_available() else 'cpu'
}
assert config['EMB_SIZE'] % config['N_ATTENTION_HEADS'] == 0

used_dataset_size = 100000

wandb.init(
    project='custom-21M',
    config=config
)
text_table = wandb.Table(columns=['epoch', 'loss', 'predicted text'])

"""## Config for training"""

load_model = False

load_df = False

"""# Dataset

## Download the dataset
"""

dataset = load_dataset("roneneldan/TinyStories")

"""## Build the Vocabulary"""

# def preprocess_text(text):
#     # Split text into sentences
#     sentences = nltk.sent_tokenize(text)

#     punctuation_pattern = r"[^\w\s]"

#     # Add <SOS> and <EOS> tokens to each sentence and remove punctuation
#     processed_sentences = [f"{re.sub(punctuation_pattern, '', sentence).strip()}" for sentence in sentences]

#     # Join sentences back into a single string
#     return " ".join(processed_sentences)

# # Update the vocabulary building function to include this preprocessing
# def build_vocabulary(dataset_dict, vocab_size=50, num_samples=None):
#     # Initialize a counter for word frequencies
#     word_counter = Counter()

#     # Use tqdm to add a progress bar for the iteration
#     data = dataset_dict['train']['text']

#     # Randomly sample num_samples if specified
#     if num_samples:
#         data = random.sample(data, num_samples)

#     # Tokenize and clean text using the tokenizer and update word frequencies
#     for text in tqdm(data, desc="Building vocabulary", unit="text"):
#         processed_text = preprocess_text(text.lower())
#         tokens = [token.replace('Ġ', '') for token in tokenizer.tokenize(processed_text)]
#         word_counter.update(tokens)

#     # Get the most common tokens and create a vocabulary dictionary
#     vocab_dict = {word: idx for idx, (word, _) in enumerate(word_counter.most_common(vocab_size))}

#     # Convert the vocabulary dictionary to a DatasetDict
#     vocab_dataset = DatasetDict({
#         'train': Dataset.from_dict({'word': list(vocab_dict.keys()), 'index': list(vocab_dict.values())}),
#         'validation': dataset_dict['validation']
#     })
#     return vocab_dataset

# # Example usage
# vocab_dataset = build_vocabulary(dataset, vocab_size=9996)
# print(vocab_dataset['train'][:10])  # Print the first 10 tokens from the vocabulary dataset

"""## Saving the Vocabulary"""

# vocab_dataset.save_to_disk('/kaggle/working/vocab_dict_v2')

"""## Loading the Vocabulary"""

loaded_vocab_dataset = DatasetDict.load_from_disk(config['VOCAB_DIRNAME'])

custom_vocab = loaded_vocab_dataset['train']['word']
new_vocab_size = len(custom_vocab)
print(new_vocab_size)

custom_vocab_dict = {word: idx for idx, word in enumerate(custom_vocab)}
if "[UNK]" not in custom_vocab_dict:
    print("Adding [UNK] token to the vocabulary.")
    custom_vocab_dict["[UNK]"] = len(custom_vocab_dict)

"""## Split the dataset"""

sampled_dataset = dataset['train'].train_test_split(train_size=0.8, test_size=0.2)
train_dataset, val_dataset = sampled_dataset['train'].select(range(int(0.8 * used_dataset_size))), sampled_dataset['test'].select(range(int(0.2 * used_dataset_size)))

"""# Model and tokenizer

## Model
"""



class Transformer21MFinalSingleLayer(nn.Module):
    def __init__(self, config=None):
        super(Transformer21MFinalSingleLayer, self).__init__()

        self.device = config['DEVICE']

        # Embedding layer
        self.embedding = nn.Embedding(config['VOCAB_SIZE'], config['EMB_SIZE']).to(self.device)

        # Positional encoding
        self.positional_encoding = nn.Parameter(torch.zeros(1, config['MAX_LENGTH'], config['EMB_SIZE'])).to(self.device)

        encoder_layer = TransformerEncoderLayer(d_model=config['EMB_SIZE'], nhead=config['N_ATTENTION_HEADS'], dim_feedforward=config['DIM_FEEDFORWRD'], dropout=config['DROPOUT'])
        decoder_layer = TransformerDecoderLayer(d_model=config['EMB_SIZE'], nhead=config['N_ATTENTION_HEADS'], dim_feedforward=config['DIM_FEEDFORWRD'], dropout=config['DROPOUT'])

        self.transformer_encoder = TransformerEncoder(encoder_layer, num_layers=config['N_ENCODER_BLOCKS']).to(self.device)
        self.transformer_decoder = TransformerDecoder(decoder_layer, num_layers=config['N_DECODER_BLOCKS']).to(self.device)

        # Output linear layer
        self.fc_out = nn.Linear(config['EMB_SIZE'], config['VOCAB_SIZE']).to(self.device)

        self.logits = None

    def forward(self, src, past_key_values=None):
        # Move src to the correct device
        src = src.to(self.device)

        # Shift src and create tgt to be aligned in length with src
        tgt = src.clone()

        # Embedding and positional encoding
        src = self.embedding(src) + self.positional_encoding[:, :src.size(1), :]
        tgt = self.embedding(tgt) + self.positional_encoding[:, :tgt.size(1), :]

        # Pass through the encoder
        memory = self.transformer_encoder(src)

        # Pass through the decoder
        output = self.transformer_decoder(tgt, memory)

        # Output layer to vocab logits
        logits = self.fc_out(output)

        self.logits = logits

        self.block_size = config['BLOCK_SIZE']

        return self.logits # Shape: (batch_size, sequence_length, vocab_size)


    def generate(self, idx, max_new_tokens):
        self.eval()  # Ensure the model is in evaluation mode
        for _ in range(max_new_tokens):
            # Crop idx to the last block_size tokens
            idx_cond = idx[:, -self.block_size:]
            # Get the predictions
            logits = self(idx_cond)  # Only use logits (ignore loss)
            # Focus only on the last time step
            logits = logits[:, -1, :]  # (B, VOCAB_SIZE)
            # Apply softmax to get probabilities
            probs = F.softmax(logits, dim=-1)  # (B, VOCAB_SIZE)
            # Sample from the distribution
            idx_next = torch.multinomial(probs, num_samples=1)  # (B, 1)
            # Append the sampled index to the running sequence
            idx = torch.cat((idx, idx_next), dim=1)  # (B, T+1)
        return idx

# # Define GPT-2 Architecture

# class GPT2FromScratch(nn.Module):
#     def __init__(self, config):
#         super(GPT2FromScratch, self).__init__()
#         self.embeddings = nn.Embedding(config["VOCAB_SIZE"], config["EMB_SIZE"])
#         self.blocks = nn.ModuleList([
#             nn.TransformerEncoderLayer(
#                 d_model=config["EMB_SIZE"],
#                 nhead=config["N_ATTENTION_HEADS"],
#                 dim_feedforward=config["DIM_FEEDFORWRD"],
#                 activation='gelu'
#             )
#             for _ in range(config["N_DECODER_BLOCKS"])
#         ])
#         self.final_norm = nn.LayerNorm(config["EMB_SIZE"])
#         self.head = nn.Linear(config["EMB_SIZE"], config["VOCAB_SIZE"])

#     def forward(self, x):
#         x = self.embeddings(x)
#         for block in self.blocks:
#             x = block(x)
#         x = self.final_norm(x)
#         return self.head(x)

# LoRA Layer Integration for Low-Rank Adaptation on the final layer

# class LoRA(nn.Module):
#     def __init__(self, layer, rank=4):
#         super(LoRA, self).__init__()
#         self.layer = layer
#         self.rank = rank
#         self.lora_A = nn.Linear(layer.in_features, rank, bias=False)
#         self.lora_B = nn.Linear(rank, layer.out_features, bias=False)
#         nn.init.normal_(self.lora_A.weight, std=0.02)
#         nn.init.normal_(self.lora_B.weight, std=0.02)

#     def forward(self, x):
#         return self.layer(x) + self.lora_B(self.lora_A(x))

# class GPT2WithLoRA(nn.Module):
#     def __init__(self, config):
#         super(GPT2WithLoRA, self).__init__()
#         self.model = GPT2FromScratch(config)
#         self.model.head = LoRA(self.model.head)

#     def forward(self, x):
#         logits = self.model(x)
#         return {'logits': logits}  # Return a dictionary with logits

#     def generate(self, input_ids, max_length=50, **kwargs):
#         output = input_ids
#         for _ in range(max_length):
#             logits = self.forward(output)['logits']
#             next_token = torch.argmax(logits[:, -1], dim=-1).unsqueeze(-1)
#             output = torch.cat((output, next_token), dim=1)
#         return output

"""## Tokenizer"""

# Create a tokenizer from scratch with custom vocab
tokenizer = Tokenizer(models.WordLevel(vocab=custom_vocab_dict, unk_token="[UNK]"))
base_tokenizer = AutoTokenizer.from_pretrained("roneneldan/TinyStories-1Layer-21M")
# Set up pre-tokenizer, normalizer, and decoder (as used in most tokenizers)
tokenizer.normalizer = normalizers.Lowercase()
tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
tokenizer.decoder = decoders.WordPiece()

# Save the tokenizer to a file
tokenizer.save("custom_tokenizer.json")

# Load this tokenizer into a PreTrainedTokenizerFast
custom_tokenizer = PreTrainedTokenizerFast(
    tokenizer_file="custom_tokenizer.json",
    model_max_length=base_tokenizer.model_max_length
)

# Add special tokens if needed
custom_tokenizer.add_special_tokens({'additional_special_tokens': ['<sos>', '<eos>']})
custom_tokenizer.add_special_tokens({'pad_token': '[PAD]'})
# Save the custom tokenizer
custom_tokenizer.save_pretrained("custom_tokenizer")

# Reload and print the vocabulary size to confirm
custom_tokenizer = AutoTokenizer.from_pretrained("custom_tokenizer")
print(f"Custom tokenizer vocabulary size: {custom_tokenizer.vocab_size}")

"""## Tokenize the dataset"""

# Tokenization function for HuggingFace dataset
def tokenize_function(examples):
    return custom_tokenizer(examples["text"], padding="max_length", truncation=True, max_length=config['BLOCK_SIZE'])

train_dataset = train_dataset.map(tokenize_function, batched=True)
val_dataset = val_dataset.map(tokenize_function, batched=True)

"""## Loading the dataset"""

# Convert tokenized dataset to PyTorch tensors
train_dataset.set_format(type='torch', columns=['input_ids'])
val_dataset.set_format(type='torch', columns=['input_ids'])

train_loader = data.DataLoader(train_dataset, batch_size=config['BATCH_SIZE'], shuffle=True)
val_loader = data.DataLoader(val_dataset, batch_size=config['BATCH_SIZE'], shuffle=False)

print(len(custom_tokenizer))

"""# Training the model

## Initializing the model
"""

# model = LSTM21MModel(config)

# model = AutoModelForCausalLM.from_pretrained("roneneldan/TinyStories-1Layer-21M")

model = Transformer21MFinalSingleLayer(config)

# model = GPT2WithLoRA(config)

model = model.to(config['DEVICE'])

# model = prepare_model_for_kbit_training(model)

# lora_config = LoraConfig(
#     r=4,                    # LoRA rank
#     lora_alpha=16,          # Alpha scaling factor
#     target_modules=["fc_out"],  # Only apply LoRA on specific target modules
#     lora_dropout=0.1,       # Dropout for LoRA layers
#     task_type="CAUSAL_LM"   # Task type
# )

total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"Total Trainable Parameters: {total_params}")

"""## Optimizer and Loss Function"""

optimizer = torch.optim.Adam(model.parameters(), lr=config['LR'])
loss_fn = torch.nn.CrossEntropyLoss()

"""## Evaluation function for validation set"""

@torch.no_grad()
def eval_model(training_model: torch.nn.Module, val_loader: torch.utils.data.DataLoader):
    training_model.eval()
    losses = torch.zeros(config['EVAL_ITER'])
    for k in range(config['EVAL_ITER']):
        batch = next(iter(val_loader))  # Get the batch as a single value
        s_val = batch['input_ids'].to(config['DEVICE'])  # Access 'input_ids' from the batch
        t_val = s_val[:, 1:].clone()  # Shift for language model prediction
        s_val = s_val[:, :-1]  # Remove last token from source

        # Forward pass through the model
        val_output = training_model(s_val)
        val_logits = val_output  # Access logits from the model's output

        # Reshape logits and targets
        val_logits = val_logits.view(s_val.size(0) * s_val.size(1), config['VOCAB_SIZE'])
        t_val = t_val.view(s_val.size(0) * s_val.size(1))

        # Compute the loss
        losses[k] = torch.nn.functional.cross_entropy(val_logits, t_val).item()

    training_model.train()
    return losses.mean()

"""## Training function"""

def train_model(model, train_loader, val_loader, optimizer, config, loss_fn):
    """
    Trains the model and logs the training and validation losses, with progress tracking using tqdm.
    """

    best_val_loss = float('inf')
    patience_counter = 0

    try:
        for epoch in range(config['EPOCHS']):
            model.train()
            epoch_loss = 0

            epoch_progress = tqdm(train_loader, desc=f"Training Epoch {epoch+1}/{config['EPOCHS']}: ", leave=False)

            for b_idx, batch in enumerate(epoch_progress):
                sources = batch['input_ids'].to(config['DEVICE'])
                targets = sources[:, 1:].clone().to(config['DEVICE'])  # Shift for language model prediction
                sources = sources[:, :-1]  # Remove last token from source
                logits = model(sources)  # Access logits from the model output

                # Get the actual batch size and sequence length
                batch_size = sources.size(0)
                seq_length = sources.size(1)

                # Reshape logits and targets
                # logits = logits.view(batch_size * seq_length, config['VOCAB_SIZE'])
                # targets = targets.view(batch_size * seq_length)
                logits = logits.view(-1, config['VOCAB_SIZE'])  # shape: (batch_size * seq_length, vocab_size)
                targets = targets.view(-1)

                loss = loss_fn(logits, targets)
                wandb.log({"loss": loss.item()})
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()
                avg_loss = epoch_loss / (b_idx + 1)
                epoch_progress.set_postfix(training_loss=avg_loss)

            avg_epoch_loss = epoch_loss / len(train_loader)
            print(f"Epoch {epoch+1}/{config['EPOCHS']} completed with average training loss: {avg_epoch_loss}")

            val_loss = eval_model(model, val_loader)
            print(f"Validation loss after {epoch+1} epochs: {val_loss}")
            wandb.log({"val_loss": val_loss})

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                print(f"New best validation loss: {val_loss}.")
            else:
                patience_counter += 1
                print(f"No improvement in validation loss. Patience counter: {patience_counter}")

            if patience_counter >= config['PATIENCE']:
                print("Early stopping triggered.")
                break

    except KeyboardInterrupt:
        print("Training interrupted.")
    print("Training completed.")

"""## Running the training loop"""

if not load_model:
    train_model(model, train_loader, val_loader, optimizer, config, loss_fn)

"""## Saving the model"""

model_req_path = config['WORKING_DIR']+'/model'

if not load_model:
    if not os.path.exists(model_req_path):
        os.mkdir(model_req_path)

    torch.save({'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict()
                }, model_req_path+'/'+config['MODEL_NAME']+'.pt')

    print("Model saved!")

"""## Loading the model"""

if load_model and os.path.exists(config['LOAD_MODELPATH']):
    checkpoint = torch.load(config['LOAD_MODELPATH'], weights_only=True)
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    print("Loaded the model!")
elif not os.path.exists(config['LOAD_MODELPATH']):
    print("Model directory not found! Please check the path.")

"""# Testing the model

## Functions for generating and scoring the outputs
"""

def prepare_input(text, tokenizer, device, block_size=128):
    # Tokenize and encode the input text
    inputs = tokenizer(
        text, return_tensors="pt", padding="max_length",
        truncation=True, max_length=block_size
    )
    # Move input tensors to the appropriate device
    return {key: val.to(device) for key, val in inputs.items()}

# def generate_text(model, tokenizer, input_text, config):
#     # Prepare the input
#     inputs = prepare_input(input_text, tokenizer, config["DEVICE"], config["BLOCK_SIZE"])

#     # Generate text
#     output_ids = model.generate(
#         inputs["input_ids"],
#         max_new_tokens=config['MAX_OUT_TOKENS'],  # max tokens to generate
#         pad_token_id=tokenizer.pad_token_id,  # Ensure proper padding
#         eos_token_id=tokenizer.eos_token_id,  # End generation on EOS
#         do_sample=True,  # Enable sampling for variety in output
#         temperature=0.7,  # Adjust temperature for randomness in sampling
#         top_k=50,  # Limit to top-k tokens to avoid unlikely predictions,
#         min_length=10
#     )

#     # Decode the generated IDs to text
#     generated_text = tokenizer.decode(output_ids[0], skip_special_tokens=True)
#     return generated_text

def generate_text(model, tokenizer, input_text, config):
    # Tokenize the input text
    input_ids = tokenizer.encode(input_text, return_tensors="pt").to(config["DEVICE"])

    # Generate text using the model's `generate` method
    output_ids = model.generate(
        input_ids,
        max_new_tokens=config['MAX_OUT_TOKENS']  # Max tokens to generate
    )

    # Decode the generated IDs to text
    generated_text = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    return generated_text

def evaluate_text_gemini(generated_text):
    # Use the generative model directly for evaluation
    model2 = gemini_ai.GenerativeModel("gemini-1.5-flash")

    # Generate content and get the response
    response = model2.generate_content(generated_text, request_options=RequestOptions(retry=retry.Retry(initial=10, multiplier=2, maximum=60, timeout=300)))

    # Check if response contains valid content
    if response.candidates:
        eval_response = response.candidates[0].content.parts[0].text  # Get the text of the first candidate
        return eval_response
    else:
        print("No valid candidates in the response. Check the generated text or API settings.")
        return None

"""## Lists of input prompts (generated by ChatGPT)"""

input_texts_list = [
    "In a bustling city filled with secrets, a shadow loomed.",
    "High in the mountains, a lone traveler braved the storm.",
    "Beneath the waves, in a hidden underwater kingdom, life thrived.",
    "It was a quiet night until the distant howls broke the silence.",
    "In a world where dragons flew free, danger was never far.",
    "On a small farm, a young girl discovered a mysterious egg.",
    "In a town where everyone whispered, the new stranger caused a stir.",
    "Under the light of the full moon, something magical began to stir.",
    "In a time of peace, a hidden evil began to rise.",
    "Amidst the golden sands of the desert, a lost caravan wandered.",
    "In the heart of the enchanted forest, a hidden village thrived.",
    "Aboard a ship sailing unknown seas, the crew faced a peculiar sight.",
    "In a world where animals spoke, a young boy sought adventure.",
    "Deep within the icy tundra, an ancient secret lay buried.",
    "On a stormy night, a stranger knocked at the castle door.",
    "In a village plagued by mysteries, a young detective took charge.",
    "Across the galaxy, explorers marveled at a new world.",
    "Underneath the quiet streets, a hidden society had formed.",
    "Long ago, a powerful wizard disappeared without a trace.",
    "At the edge of the world, a brave crew faced the unknown.",
    "In a city that never slept, two souls crossed paths unexpectedly.",
    "In a school for magical creatures, new students arrived.",
    "Hidden in the clouds, a floating kingdom kept its secrets.",
    "Far in the distant future, humanity encountered its first alien.",
    "Under a blanket of stars, two friends made a promise.",
    "In a library of forgotten books, a mysterious journal appeared.",
    "Aboard a train that never stopped, secrets unraveled slowly.",
    "Amid a sea of stars, a lone spaceship drifted in silence.",
    "In a kingdom of snow and ice, a prophecy was foretold.",
    "Deep in the jungle, explorers discovered a glowing stone.",
    "In a village under a curse, a hero was born.",
    "At the dawn of time, the first humans encountered magic.",
    "On a distant moon, an outpost signaled for help.",
    "In a quiet town, every night brought new mysteries.",
    "Beneath the great pyramids, an ancient secret was uncovered.",
    "In a world without color, a single red flower bloomed.",
    "On a ship lost at sea, whispers of an island spread.",
    "In the middle of nowhere, a door to another world appeared.",
    "In a castle of mirrors, reflections began to act strangely.",
    "On the edge of a cliff, a young prince made a fateful decision.",
    "In a forest where time stood still, a visitor arrived.",
    "In a kingdom ruled by animals, a lion declared his rule.",
    "In a world where wishes came true, a girl wished for more time.",
    "In a school where shadows came alive, mysteries abounded.",
    "In a library that seemed endless, a strange book was found.",
    "On a small island, villagers began to notice odd happenings.",
    "In the great desert, a treasure was hidden for centuries.",
    "In a city beneath the earth, a new ruler emerged.",
    "In a world divided by seasons, an eternal summer began.",
    "At the top of a mountain, a temple held the key to truth.",
    "In a town where time rewound each day, mysteries deepened.",
    "On a snowy peak, two climbers discovered an ancient statue.",
    "In a mansion where paintings moved, a mystery unraveled.",
    "At the crossroads of realms, two adventurers met.",
    "In a school hidden in the woods, every student had a secret.",
    "In a town of endless rain, hope was a rare sight.",
    "On a train bound for nowhere, strange passengers arrived.",
    "In a forest where trees whispered, a path emerged.",
    "In a world where stars guided destiny, a comet foretold change.",
    "In a lonely tower, a forgotten sorceress waited.",
    "At the edge of a lake, the reflection showed another world.",
    "In a world beneath the clouds, legends of the sky spread.",
    "In a kingdom of night, a lone warrior sought dawn.",
    "In a garden of eternal flowers, time stood still.",
    "On an island that disappeared each night, a story began.",
    "In a city that glittered like gold, shadows lurked.",
    "In a land where dreams came alive, a nightmare was born.",
    "On the longest night, a hero's journey began.",
    "In a kingdom lost to time, an old legend resurfaced.",
    "In a forest cloaked in fog, paths led nowhere.",
    "In a small shop, a mysterious item granted wishes.",
    "On the day the sun didn't rise, fear spread.",
    "In a town with no maps, wanderers were welcome.",
    "Under a sky of falling stars, two souls met.",
    "In a house with endless rooms, a mystery unraveled.",
    "In a town where no one aged, secrets were kept.",
    "In the middle of the ocean, a floating castle appeared.",
    "At the heart of the desert, a lone tree bloomed.",
    "In a world ruled by music, silence was feared.",
    "On the night of the festival, a strange guest arrived.",
    "In a land where darkness ruled, a light began to shine.",
    "In a city where everyone wore masks, truths hid.",
    "In a world of whispers, silence was a power.",
    "On the eve of battle, a hero was forged.",
    "In a castle of glass, a kingdom looked on.",
    "In the kingdom of echoes, a voice was heard.",
    "In a forest where dreams came true, nightmares hid.",
    "In a town with endless winters, a new day dawned.",
    "In a realm where seasons changed daily, stories grew.",
    "Under the gaze of ancient gods, mortals lived.",
    "In a world frozen in time, a clock began to tick.",
    "In a library of the lost, an old tale was read.",
    "In a meadow under starlight, two friends found magic.",
    "In a city where clocks ran backward, futures changed.",
    "In a kingdom ruled by children, a new game began.",
    "In a land where the moon never rose, stars told tales.",
    "In the far north, where the aurora danced, legends lived.",
    "At the edge of eternity, two lovers met.",
    "In a village of music, silence brought fear.",
    "In a world where memories could be traded, one boy remembered."
]

"""## Prompts for scoring the output by Gemini"""

step_1_static = (
    "The following exercise, the student is given the beginning of a story. The student needs to complete it into a full story. "
    "The exercise tests the student’s language abilities and creativity. The symbol *** marks the separator between the "
    "prescribed beginning and the student’s completion: "
)

step_2 = (
    "Please provide your general assessment about the part written by the student (the one after the *** symbol). "
    "Only give the ratings without description and overall could be omitted"
    "Do not give explainations for the ratings."
    "Give them in one single line, separated by semi-colon."
    "Keep the fields for the output consistent, that is keep all the fields mentioned in the next sentence. "
    "Grammer: ; Consistency: ; Creativity: ; Plot: ; Age group: "
    "Is it grammatically correct? Is it consistent with the beginning of the story? Pay special attention to whether the "
    "student manages to complete the sentence which is split in the middle by the separator ***."
)

step_3 = (
    "Now, grade the student’s completion in terms of grammar, creativity, consistency with the story’s beginning and "
    "whether the plot makes sense. Moreover, please provide your best guess of what the age of the student might be, "
    "as reflected from the completion. Choose from possible age groups: A: 3 or under. B: 4-5. C: 6-7. D: 8-9. E: 10-12. F: 13-16. "
    "e.g. Grammar: 8/10; Consistency: 7/10; Creativity: 7/10; Plot: 7/10; Age group: E (10-12)"
)

"""## Getting the scores"""

pattern = r"Grammar: (\d+)/10; Consistency: (\d+)/10; Creativity: (\d+)/10; Plot: (\d+)/10; Age group: ([A-Z])"
score_list = []
count = 0

if not load_df:
    for input_text in input_texts_list:
        output_text = generate_text(model, custom_tokenizer, input_text, config)
        dynamic_part = f"{input_text} Story begins here:***  {''.join(output_text)}. *** The story ends here"
        final_prompt = f"{step_1_static}{dynamic_part}\n{step_2}\n{step_3}"
        gemini_generated_response = evaluate_text_gemini(final_prompt)
        if gemini_generated_response == "Please provide the student's story completion.  I need the text after the \"***\" to grade it." or gemini_generated_response == "Please provide the student's completion of the story.  I need that text to be able to grade it.":
            print(final_prompt, gemini_generated_response)
        gemini_generated_response = gemini_generated_response.strip()
        count += 1

        print(f"{count}- {input_text}; {gemini_generated_response}")

        match = re.search(pattern, gemini_generated_response)
        if match:
            grammar, consistency, creativity, plot, age_group = match.groups()
            score_list.append([input_text, int(grammar), int(consistency), int(creativity), age_group])
        else:
            score_list.append([input_text, 0, 0, 0, "DNF"])
        # print(f"Number of prompts appended: {count}")

"""## Putting them in Pandas dataframe"""

df = pd.DataFrame(score_list, columns=["Input Prompt", "Grammar", "Consistency", "Creativity", "Plot", "Age Group"])

df

"""## Saving the Pandas Dataframe"""

result_req_path = config['WORKING_DIR']+'/result'

if not load_df:
    if not os.path.exists(result_req_path):
        os.mkdir(result_req_path)

    df.to_pickle(result_req_path+'/'+'rating_df_'+config['MODEL_NAME']+'.pkl')

    print("Dataframe saved!")

"""## Loading the Pandas Dataframe"""

if load_df and os.path.exists(config['DF_PATH']):
    df = pd.read_pickle(config['DF_PATH'])
    print("Loaded dataframe!")
else:
    if not load_df:
        pass
    elif not os.path.exists(config['DF_PATH']):
        print("Result directory not found! Please check the path.")


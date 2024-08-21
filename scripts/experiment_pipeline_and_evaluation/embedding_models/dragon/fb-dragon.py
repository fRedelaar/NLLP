import argparse
import pandas as pd
from transformers import AutoTokenizer, AutoModel
import numpy as np
import torch
import os
from scripts.helpers.TREC_EVAL_recall_at_k import evaluate_and_write_results


def retrieve_docs_for_questions_dragon(qa_df, k):
    # Load the CSV file
    csv_file_path = "../../../../datasets/knowledge_corpus/large_corpus/knowledge_corpus_large.csv"
    df = pd.read_csv(csv_file_path)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    # Extract the text content from the DataFrame
    df['combined_text'] = df.apply(lambda row: f"{row['DOC_ID']} {row['text']}", axis=1)
    documents = df['combined_text'].tolist()

    # Use something such as the code below, to include metadata:
    # df['combined_text'] = df.apply(lambda row: f"{row['DOC_ID']} {row['law_id']} {row[
    # 'law_name']} {row['hoofdstuk']} {row['hoofdstuk_titel']} {row['afdeling']} {row['afdeling_titel']} {row[
    # 'paragraaf']} {row['paragraaf_titel']} {row['subparagraaf_titel']} {row['titel_titel']} {row['artikel']} {row[
    # 'article_name']} {row['text']}", axis=1)

    # Initialize the DRAGON tokenizer and models
    tokenizer = AutoTokenizer.from_pretrained('facebook/dragon-plus-query-encoder')
    query_encoder = AutoModel.from_pretrained('facebook/dragon-plus-query-encoder').to(device)
    context_encoder = AutoModel.from_pretrained('facebook/dragon-plus-context-encoder').to(device)

    # Check if embeddings file exists
    embeddings_file = 'fb_dragon_context_embeddings_no_metadata_large_corpus.npy'
    if os.path.exists(embeddings_file):
        # Load embeddings from file
        print("Embedding file found!")
        doc_embeddings = np.load(embeddings_file)
    else:
        # Encode the documents in batches
        print("No embedding file found. Creating new one.")
        batch_size = 32
        doc_embeddings = []

        for i in range(0, len(documents), batch_size):
            batch_documents = documents[i:i + batch_size]
            ctx_input = tokenizer(batch_documents, padding=True, truncation=True, return_tensors='pt').to(device)
            batch_embeddings = context_encoder(**ctx_input).last_hidden_state[:, 0, :].detach().cpu().numpy()
            doc_embeddings.extend(batch_embeddings)

        doc_embeddings = np.array(doc_embeddings)
        np.save(embeddings_file, doc_embeddings)

    relevant_docs = []
    for idx, row in qa_df.iterrows():
        query = row['question']
        query_input = tokenizer(query, return_tensors='pt').to(device)
        query_embedding = query_encoder(**query_input).last_hidden_state[:, 0, :].detach().cpu().numpy()

        # Compute dot product similarity between query and each document
        cosine_scores = np.dot(doc_embeddings, query_embedding.T).squeeze()

        # Get the top k results
        top_results = np.argsort(cosine_scores)[-k:][::-1]
        doc_ids = [df.iloc[idx]['DOC_ID'] for idx in top_results]
        relevant_docs.append(doc_ids)

    return relevant_docs

def retrieve_relevant_docs(k, QA):
    relevant_docs = retrieve_docs_for_questions_dragon(QA, k)
    print(relevant_docs)
    return relevant_docs, QA

def main():
    parser = argparse.ArgumentParser(description="Script to retrieve and generate answers.")
    parser.add_argument("--k", type=int, default=5, help="Number of documents to retrieve per query.")
    args = parser.parse_args()

    configurations = [
        {"k": 3, "recall_metric": "recall_3"},
        {"k": 5, "recall_metric": "recall_5"},
        {"k": 10, "recall_metric": "recall_10"},
    ]

    # Load data only once
    QA = pd.read_csv("../../../../datasets/QA_set/QA_set_102_largecorpus.csv")

    results_dir = "../../../../experiment_results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    for config in configurations:
        print(f"Results using {config['recall_metric']}")
        relevant_docs, QA_loaded = retrieve_relevant_docs(k=config['k'], QA=QA)
        evaluate_and_write_results(relevant_docs, QA_loaded, recall_metric=config['recall_metric'], k=config['k'], modelname="fb-dragon")

if __name__ == "__main__":
    main()

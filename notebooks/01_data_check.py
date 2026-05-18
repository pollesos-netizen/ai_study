import pandas as pd

df = pd.read_csv("data/privacy_sentence_sample.csv")

print(df.head())

print(df["label"].value_counts())

print(df["category"].value_counts())

print(df.isna().sum())

df["text_length"] = df["text"].str.len()

print(df[["text", "text_length"]].head())
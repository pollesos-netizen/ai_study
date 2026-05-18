import pandas as pd

df = pd.read_csv("data/privacy_sentence_sample.csv")

df.head()

df["label"].value_counts()

df["category"].value_counts()

df.isna().sum()

df["text_length"] = df["text"].str.len()
df[["text", "text_length"]].head()
import streamlit as st
import json
import asyncio
from pathlib import Path

# Allow local `streamlit run src/app/modules/DPS/streamlit_app.py`
# to resolve imports from the `src` package root without requiring PYTHONPATH.
import sys

SRC_ROOT = Path(__file__).resolve().parents[3]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.modules.DPS.pipeline import run_pipeline

st.set_page_config(
    page_title="SMIF Data Pipeline",
    layout="wide"
)

st.title("Smart Market Insight Feed")
st.subheader("News Data Ingestion")

st.markdown("""
Upload JSON files OR run the pipeline on sample JSON documents stored locally.
""")

input_mode = st.radio(
    "Choose Input Source",
    ["Upload JSON Files", "Run Sample Files"]
)

def load_json_files(files):
    docs = []
    for f in files:
        data = json.load(f)

        if isinstance(data, list):
            docs.extend(data)
        else:
            docs.append(data)

    return docs


def load_json_from_folder(folder_path):
    docs = []
    path = Path(folder_path)
    print(path)
    for file in path.glob("*.json"):
        with open(file, "r") as f:
            data = json.load(f)

            if isinstance(data, list):
                docs.extend(data)
            else:
                docs.append(data)

    return docs

if input_mode == "Upload JSON Files":

    uploaded_files = st.file_uploader(
        "Upload JSON Files",
        type=["json"],
        accept_multiple_files=True
    )

    if uploaded_files:
        st.success(f"{len(uploaded_files)} files uploaded")

        if st.button("Start Data Pipeline"):

            with st.spinner("Processing files through pipeline..."):

                docs = load_json_files(uploaded_files)

                st.write(f"Total documents detected: {len(docs)}")

                try:
                    pipeline_result = asyncio.run(run_pipeline(docs))

                    st.success("Pipeline completed successfully")

                    st.json({
                        "documents_processed": len(docs),
                        "pipeline_status": pipeline_result
                    })

                except Exception as e:
                    st.error("Pipeline execution failed")
                    st.exception(e)

if input_mode == "Run Sample Files":

    SAMPLE_FOLDER = Path(__file__).resolve().parent/"news_raw"

    if st.button("Run Sample Pipeline"):

        with st.spinner("Processing sample files..."):

            docs = load_json_from_folder(SAMPLE_FOLDER)

            st.write(f"Sample documents detected: {len(docs)}")

            try:
                pipeline_result = asyncio.run(run_pipeline(docs))

                st.success("Pipeline completed successfully")

                st.json({
                    "documents_processed": len(docs),
                    "pipeline_status": pipeline_result
                })

            except Exception as e:
                st.error("Pipeline execution failed")
                st.exception(e)

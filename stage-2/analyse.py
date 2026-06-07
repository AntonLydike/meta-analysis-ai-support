from bz2 import compress
import os
import glob
from dataclasses import dataclass
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import pypdfium2 as pdfium
from concurrent.futures import ThreadPoolExecutor
import zlib


@dataclass
class Document:
    id: int
    title: str
    path: str
    filesize: int  # in bytes
    year: int | None = None


def analyze_pdf_collection(docs: list[Document]) -> pd.DataFrame:
    """
    Scans the provided document catalog to extract structural data,
    character counts, and non-text visual complexity metrics.
    """
    records = []

    print(f"🔍 Analyzing {len(docs)} documents...")

    pool = ThreadPoolExecutor(6)

    for i, doc in enumerate(docs):
        if not os.path.exists(doc.path):
            print(f"⚠️ File not found, skipping: {doc.path}")
            continue
        try:
            pdf = pdfium.PdfDocument(doc.path)

            total_chars = 0
            total_images = 0
            page_count = len(pdf)
            total_text = []

            for page in pdf:
                # 1. Extract text metrics
                text_page = page.get_textpage()
                text = text_page.get_text_bounded()
                if text:
                    total_chars += len(text)
                    total_text.append(text)

                # 2. Extract non-text complexity (count image/vector object mappings)
                # This scans internal PDF page object layers
                try:
                    images = len(
                        [
                            obj
                            for obj in page.get_objects()
                            if obj.get_type() == pdfium.pypdfium2.PDFOBJ_IMAGE
                        ]
                    )
                    if images == 0 and len(text.strip()) < 5:
                        images += 1
                    total_images += images
                except Exception:
                    # Fallback metric if object layer is encrypted/corrupt
                    total_images += 1

            # Convert bytes to Megabytes for friendly plotting scale
            size_kb = doc.filesize / 1024

            records.append(
                obj := {
                    "id": doc.id,
                    "title": doc.title,
                    "size_kb": size_kb,
                    "char_count": total_chars,
                    "non_text_objects": total_images,
                    "page_count": page_count,
                    # Ratio metric to evaluate density profiles
                    "objects_per_thousand_chars": (
                        total_images / (total_chars / 1000 + 1)
                    ),
                    "text_content": "\n".join(total_text),
                }
            )
            pool.submit(measure_zlib_compression, obj)

        except Exception as e:
            print(f"❌ Could not analyze file ID {doc.id} ({doc.path}): {e}")
        if i % 100 == 0:
            print(
                "{:<100} {:2d}%".format(
                    "#" * int(100 * i / len(docs)),
                    int(
                        i / len(docs) * 100,
                    ),
                ),
                end="\r",
            )
    print("\ndone!")

    pool.shutdown(wait=True)

    return pd.DataFrame(records)


def measure_zlib_compression(obj: dict):
    data = obj["text_content"].encode()
    compressed = zlib.compress(data, 7)
    obj["text_compression_ratio"] = len(data) / len(compressed)
    obj["compressed_size"] = len(compressed)


def generate_and_save_plots(
    df: pd.DataFrame, output_pdf_path: str = "pdf_collection_analysis.pdf"
):
    """
    Generates a 3-panel subplot layout mapping out:
    1. Cumulative fraction of File Sizes (ECDF)
    2. Cumulative fraction of Extractable Text (ECDF)
    3. Log-Log Relationship between Text and Estimated Image Weights
    """
    if df.empty:
        print("Empty DataFrame. Plots cannot be generated.")
        return

    # Set up styling aesthetics
    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(
        "PDF Document Corpus Characteristics Profile",
        fontsize=16,
        fontweight="bold",
        y=1.02,
    )

    # Subplot 1: Cumulative Fraction of File Size (ECDF)
    sns.ecdfplot(
        data=df,
        x="size_kb",
        ax=axes[0],
        color="#2b5c8f",
        linewidth=2.5,
        log_scale=[True, False],
    )
    axes[0].set_title(
        "Cumulative Fraction of File Size", fontsize=12, fontweight="bold"
    )
    axes[0].set_xlabel("File Size (KB)")
    axes[0].set_ylabel("Proportion of Corpus (0.0 to 1.0)")

    # Subplot 2: Cumulative Fraction of Extractable Text Content (ECDF)
    sns.ecdfplot(
        data=df,
        x="char_count",
        ax=axes[1],
        color="#2ca02c",
        linewidth=2.5,
        log_scale=[True, False],
    )
    axes[1].set_title(
        "Cumulative Fraction of Text Volume", fontsize=12, fontweight="bold"
    )
    axes[1].set_xlabel("Character Count (Total Text)")
    axes[1].set_ylabel("Proportion of Corpus (0.0 to 1.0)")

    # plot 3: plot ecdf of text_compression_ratio
    sns.ecdfplot(
        data=df,
        x="text_compression_ratio",
        ax=axes[2],
        color="#ccdd00",
        linewidth=2.5,
    )
    axes[2].set_title(
        "Cumulative Fraction of Text Compression Ratio (zlib)",
        fontsize=12,
        fontweight="bold",
    )
    axes[2].set_xlabel("Text Compression Ratio (zlib)")
    axes[2].set_ylabel("Proportion of Corpus (0.0 to 1.0)")

    ## Subplot 3: Image Weight vs Text Content Relationship (Strict Double-Log Scale)
    ## Add a small offset so 0 values safely plot on log scale without dropping
    # df_plot = df.copy()

    # sns.scatterplot(
    #    data=df_plot,
    #    x="char_count",
    #    y="non_text_objects",
    #    hue="size_kb",
    #    size="page_count",
    #    palette="viridis",
    #    sizes=(40, 400),
    #    alpha=0.2,
    #    ax=axes[2],
    # )

    ## Enforce logarithmic scale constraints strictly on both dimensions
    # axes[2].set_title(
    #    "Text vs. Image Density (Log-Log)", fontsize=12, fontweight="bold"
    # )
    # axes[2].set_xlabel("Character Count")
    # axes[2].set_ylabel("Number of image entities")
    # axes[2].set_yscale("log")
    # axes[2].set_xscale("log")

    ## Position legend cleanly outside the plot area
    # axes[2].legend(bbox_to_anchor=(1.05, 1), loc="upper left", title="Metrics Info")

    # Final layout adjustments and saving
    plt.tight_layout()
    plt.savefig(output_pdf_path, format="pdf", bbox_inches="tight")
    print(f"💾 Cumulative structural visualization report saved to: {output_pdf_path}")
    plt.close()


# =====================================================================
# 🚀 Demo Execution Context Block
# =====================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", nargs="?", help="Scan a specific folder")
    parser.add_argument("--df-name", default="analysis.csv")
    parser.add_argument("--plot-name", default="analysis.pdf")
    parser.add_argument(
        "--exclude-charcount",
        default=None,
        type=float,
        help="exclude based on char count",
    )
    parser.add_argument(
        "--exclude-compression",
        default=None,
        type=float,
        help="exclude based on zlib compression level",
    )
    parser.add_argument("--show-extremes")
    args = parser.parse_args()

    # Create sample dummy records matching your exact structural dataclasses
    # (In real deployment scenarios, map this array dynamically out of your file directory)
    df_results = None

    # Example: Scanning a local folder for files if they exist
    if args.scan is not None:
        mock_docs = []

        if os.path.exists(args.scan):
            file_paths = glob.glob(os.path.join(args.scan, "**/*.pdf"), recursive=True)
            for index, path in enumerate(file_paths):
                mock_docs.append(
                    Document(
                        id=index + 1,
                        title=os.path.basename(path),
                        path=path,
                        filesize=os.path.getsize(path),
                    )
                )
        else:
            print("folder not found")

        # Execute data extraction pipeline frame logic if docs exist
        if mock_docs:
            df_results = analyze_pdf_collection(mock_docs)
            df_results.to_csv(args.df_name, index=False)
            print("\n📊 Extracted Data Frame Summary Output View:")
            print(df_results.head())
    if df_results is None:
        df_results = pd.read_csv(args.df_name)

    # Output visual graphing assets reports file
    generate_and_save_plots(df_results, args.plot_name)

    if args.exclude_compression is not None or args.exclude_charcount is not None:
        df_results["excluded"] = False
        if args.exclude_compression is not None:
            df_results["excluded"] = (
                df_results["text_compression_ratio"] > args.exclude_compression
            )
        if args.exclude_charcount is not None:
            df_results["excluded"] |= df_results["char_count"] < args.exclude_charcount

        df_results.to_csv("analysis_filtered.csv", index=False)
        print(
            f"#Excluded: {df_results['excluded'].sum()}, %excluded: {df_results['excluded'].mean() * 100:.1f}%"
        )

    df_results.drop(columns=["text_content"]).to_csv("analysis_notext.csv", index=False)

    if args.show_extremes:
        # summary:
        columns_to_check = [
            "size_kb",
            "char_count",
            "non_text_objects",
            "page_count",
            "objects_per_thousand_chars",
        ]

        print("🔍 Detailed Dataset Extrema Report:\n" + "=" * 50)

        for col in columns_to_check:
            # Find row indices for min and max
            min_idx = df_results[col].idxmin()
            max_idx = df_results[col].idxmax()

            # Extract the full records
            min_row = df_results.loc[min_idx]
            max_row = df_results.loc[max_idx]

            print(f"📈 METRIC: {col}")
            print(
                f"  • MIN: {min_row[col]:.4f} -> Doc ID {min_row['id']} ('{min_row['title']}')"
            )
            print(
                f"  • MAX: {max_row[col]:.4f} -> Doc ID {max_row['id']} ('{max_row['title']}')"
            )
            print("-" * 50)

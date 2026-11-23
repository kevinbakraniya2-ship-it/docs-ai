# Docs AI: from PDF to answer

This diagram follows the student's journey. The top half prepares the PDF. The bottom half shows what happens when the student asks a question.

```mermaid
flowchart TD
    subgraph Prepare[1. Prepare the PDF]
        A[Student uploads a PDF] --> B{PDF valid and under 10 MB?}
        B -- No --> C[Show an upload error]
        B -- Yes --> D[Save it to the student's account]
        D --> E[Student opens Read text by page]
        E --> F{Selectable text available?}
        F -- Yes --> G[Extract text page by page]
        F -- No, scanned PDF --> H[Use OCR to read each page]
        G --> I[Save page text and page numbers]
        H --> I
    end

    subgraph Question[2. Find and answer]
        J[Student asks a question about this PDF] --> K[Check for saved page vectors]
        K --> L{Are vectors missing?}
        L -- Yes --> M[EmbeddingGemma creates vectors for the pages]
        L -- No --> N[Reuse saved vectors]
        M --> O[Search only this PDF in ChromaDB]
        N --> O
        O --> P[Filter out pages that do not match the topic]
        P --> Q{Relevant passages found?}
        Q -- No --> R[Show that the answer was not found]
        Q -- Yes --> S[Send passages to Qwen running locally]
        S --> T[Show the answer and source page links]
    end

    I --> J
```

## What the diagram means

1. **Upload:** Docs AI checks the PDF and saves it under the signed-in student's account.
2. **Read:** The student opens **Read text by page**. Docs AI extracts selectable text, or uses OCR for a scanned PDF, and saves the result page by page.
3. **Search:** When a question is asked, EmbeddingGemma creates any missing page vectors. ChromaDB searches the selected PDF, then Docs AI filters out pages that do not match the question's topic.
4. **Answer:** If useful passages are found, the local Qwen model writes an answer from those passages. Docs AI shows links to the source pages so the student can check the answer.
5. **No match:** If no relevant passage is found, Docs AI says it could not find the answer in that PDF.

## Deleting a PDF

From **My PDFs**, the owner can delete a document. Docs AI removes the uploaded PDF, its saved page text, and its ChromaDB vectors.

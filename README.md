# PDFPilot

AI-powered document automation tool. Upload documents and use chat commands to convert, merge, split, compress, and extract text.

The backend includes a command router, so the chat UI can send one natural-language request to `/api/process` and let the server choose the correct tool.

## Project Structure

```
PDFPilot/
├── frontend/          HTML pages (landing, login, signup, app, tools, history)
├── css/               Stylesheets (design system, components, pages)
├── js/                JavaScript (app logic, chat, file handling)
├── backend/
│   ├── main.py        FastAPI server entry point
│   ├── routes.py      API endpoints
│   └── services/      Document processing modules
│       ├── convert_service.py
│       ├── merge_service.py
│       ├── split_service.py
│       ├── compress_service.py
│       └── extract_service.py
├── uploads/           Uploaded files (auto-created)
├── outputs/           Processed files (auto-created)
├── logs/              Server logs
├── requirements.txt
└── README.md
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python -m backend.main
```

Server starts at `http://localhost:8000`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/upload` | Upload a file |
| POST | `/api/process` | Route a natural-language command to the correct document tool |
| POST | `/api/convert` | Convert document to PDF |
| POST | `/api/merge` | Merge multiple PDFs |
| POST | `/api/split` | Split PDF by page range |
| POST | `/api/compress` | Compress PDF |
| POST | `/api/extract` | Extract text from document |
| GET | `/api/download/{file}` | Download processed file |
| GET | `/api/history` | List processed files |

## Tech Stack

- **Frontend**: HTML, CSS, JavaScript
- **Backend**: Python, FastAPI
- **PDF**: PyPDF2, ReportLab, Pillow, pdf2image

## Router Mode

The current backend uses a local command router by default.

- No Gemini API key is required.
- No OpenAI API key is required.
- If you later add a hosted LLM provider, keep its API key in environment variables rather than hardcoding it.

## Notes

- `pdf2image` support may require Poppler to be installed on your machine for PDF-to-image conversion.
- OCR from images still requires a local Tesseract install if you enable `pytesseract`.
- High-fidelity `DOC/DOCX/PPT/PPTX -> PDF` conversion requires Microsoft Word or LibreOffice on the machine.
- `PDF -> DOCX/DOC` conversion requires Microsoft Word on the machine.

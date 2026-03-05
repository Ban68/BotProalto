
import PyPDF2

try:
    with open("docs/Estados internos ProAlto.pdf", "rb") as pdf_file:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        print(text)
except FileNotFoundError:
    print("Error: The file 'docs/Estados internos ProAlto.pdf' was not found in the current directory.")
except Exception as e:
    print(f"An error occurred: {e}")

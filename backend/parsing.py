import fitz
import docx
import os

def parse_pdf(file_path: str) -> str:

    try:
        with fitz.open(file_path) as doc:
            # Concatenate text from all pages
            text = "".join(page.get_text() for page in doc)
        return text
    except Exception as e:
        # Catches errors like file corruption, password protection, etc.
        raise ValueError(f"Could not read PDF file '{os.path.basename(file_path)}': {e}")

def parse_docx(file_path: str) -> str:

    try:
        doc = docx.Document(file_path)
        full_text = []

        # Extract text from paragraphs
        for para in doc.paragraphs:
            full_text.append(para.text)

        # Extract text from tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    # Append text from each cell, separated by a space
                    full_text.append(cell.text)
        
        return "\n".join(full_text)
    except Exception as e:
        raise ValueError(f"Could not read DOCX file '{os.path.basename(file_path)}': {e}")

def parse_cv(file_path: str) -> str:
    
    # First, check if the file actually exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file was not found at the specified path: {file_path}")

    # Get the file extension and convert to lower case for reliable comparison
    _, extension = os.path.splitext(file_path)
    extension = extension.lower()

    if extension == '.pdf':
        return parse_pdf(file_path)
    elif extension == '.docx':
        return parse_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: '{extension}'. Only PDF and DOCX files are supported.")

# --- Example Usage ---
# This block will only run when you execute this script directly (e.g., `python parsing.py`)
if __name__ == '__main__':
    # Create dummy files for testing purposes
    # 1. A dummy DOCX file
    try:
        doc = docx.Document()
        doc.add_paragraph("John Doe")
        doc.add_paragraph("Software Engineer with 5 years of experience.")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Skill"
        table.cell(0, 1).text = "Proficiency"
        table.cell(1, 0).text = "Python"
        table.cell(1, 1).text = "Expert"
        doc.save("dummy_cv.docx")
        print("Created dummy_cv.docx for testing.")
    except Exception as e:
        print(f"Could not create dummy DOCX. You may need to run 'pip install python-docx'. Error: {e}")


    # 2. A dummy PDF file
    try:
        pdf_doc = fitz.open()
        page = pdf_doc.new_page()
        page.insert_text((72, 72), "Jane Smith - Product Manager")
        page.insert_text((72, 92), "Experienced in agile methodologies and market analysis.")
        pdf_doc.save("dummy_cv.pdf")
        pdf_doc.close()
        print("Created dummy_cv.pdf for testing.")
    except Exception as e:
         print(f"Could not create dummy PDF. You may need to run 'pip install PyMuPDF'. Error: {e}")


    # --- Run the parsers ---
    print("\n--- Testing Parsers ---")
    
    # Test with a DOCX file
    try:
        print("\nParsing DOCX file...")
        docx_text = parse_cv('dummy_cv.docx')
        print("Successfully extracted text from DOCX:")
        print("-" * 20)
        print(docx_text)
        print("-" * 20)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")

    # Test with a PDF file
    try:
        print("\nParsing PDF file...")
        pdf_text = parse_cv('dummy_cv.pdf')
        print("Successfully extracted text from PDF:")
        print("-" * 20)
        print(pdf_text)
        print("-" * 20)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        
    # Test with an unsupported file type
    try:
        print("\nTesting unsupported file type...")
        with open("dummy_cv.txt", "w") as f:
            f.write("This is a text file.")
        parse_cv('dummy_cv.txt')
    except ValueError as e:
        print(f"Successfully caught expected error: {e}")

    # Clean up dummy files
    if os.path.exists("dummy_cv.docx"): os.remove("dummy_cv.docx")
    if os.path.exists("dummy_cv.pdf"): os.remove("dummy_cv.pdf")
    if os.path.exists("dummy_cv.txt"): os.remove("dummy_cv.txt")
    print("\nCleaned up dummy files.")

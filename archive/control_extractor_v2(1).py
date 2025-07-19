# control_extractor_v2.py

"""
Enhanced extractor for tested controls in SOC reports using GPT and adaptive techniques.
- Implements dynamic chunking and classification of text segments.
- Uses feedback mechanisms and heuristic rules for improved accuracy.
- Outputs structured JSON records for each control section.
"""

import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from backend.app.gpt_client import gpt_extract
import re

try:
    from .. import config
except Exception as import_err:
    print(f"[CONTROL_EXTRACTOR_V2] Import error: {import_err}")
    raise

# Use centralized config paths
try:
    SECTION_JSON_PATH = config.SECTION_JSON_PATH
    PDF_TXT_PATH = config.PDF_TXT_PATH
    OUTPUT_JSON_PATH = config.CONTROL_JSON_PATH
    GPT_LOG_PATH = config.CONTROL_GPT_LOG_PATH
except Exception as config_err:
    print(f"[CONTROL_EXTRACTOR_V2] Config error: {config_err}")
    logging.error(f"[CONTROL_EXTRACTOR_V2] Config error: {config_err}")
    raise

# Configure logging to overwrite the log file each time the script runs
logging.basicConfig(
    filename='data/logs/control_extractor_v2.log',
    filemode='w',  # Overwrite the log file
    level=logging.INFO,  # Set to INFO to reduce log verbosity
    format='%(asctime)s [CONTROL_EXTRACTOR_V2] %(message)s',
)

# Dynamic chunking function

def dynamic_chunking(text, initial_chunk_size=3000):
    """
    Use GPT to analyze text and determine logical breakpoints for chunking.
    """
    chunk = text[:initial_chunk_size]
    remaining_text = text[initial_chunk_size:]
    chunks = []

    logging.info(f'Initial chunk size: {len(chunk)}')

    prompt = (
        "Identify the single numeric character position in the text where each control section header starts. "
        "Do not infer or assume any details not present in the text."
    )
    response = gpt_extract(prompt, 'control_extractor')

    if not response:
        logging.error('Empty GPT response for chunking. Using default chunk size.')
        return [chunk, remaining_text]

    breakpoints = parse_breakpoints(response)

    if not breakpoints:
        logging.error('No breakpoints found in GPT response. Using default chunk size.')
        return [chunk, remaining_text]

    start = 0
    for breakpoint in breakpoints:
        chunks.append(chunk[start:breakpoint])
        start = breakpoint

    chunks.append(remaining_text)

    return chunks

# Implement parsing logic for GPT responses

def parse_breakpoints(response):
    """
    Parse GPT response to extract breakpoints.
    """
    # Example parsing logic based on the response format
    breakpoints = []
    try:
        lines = response.split('\n')
        for line in lines:
            if 'Control Section Start' in line or 'Control Section End' in line:
                # Extract the character position from the line
                parts = line.split(':')
                if len(parts) > 1:
                    position_str = parts[-1].strip()
                    # Check if the position is numeric
                    if position_str.isdigit():
                        position = int(position_str)
                        breakpoints.append(position)
                    else:
                        logging.warning(f'Non-numeric position found: {position_str}')
    except Exception as e:
        logging.error(f'Error parsing breakpoints: {e}')
    return breakpoints

# Text classification function

def classify_text_segments(chunk):
    """
    Use GPT to classify text segments within a chunk.
    """
    prompt = config.SEGMENT_CLASSIFICATION_PROMPT.format(text=chunk, context="SOC report control section")
    response = gpt_extract(prompt, 'control_extractor')

    if not response:
        logging.error('Empty GPT response for classification. Returning empty segments.')
        return []

    classified_segments = parse_classified_segments(response)

    if not classified_segments:
        logging.error('No classified segments found in GPT response. Returning empty segments.')

    return classified_segments

# Implement parsing logic for classified segments

def parse_classified_segments(response):
    """
    Parse GPT response to extract classified segments.
    """
    # Example parsing logic based on the response format
    segments = []
    try:
        lines = response.split('\n')
        current_segment = {}
        for line in lines:
            if line.startswith('Control ID:'):
                if current_segment:
                    segments.append(current_segment)
                    current_segment = {}
                current_segment['type'] = 'control_id'
                current_segment['text'] = line.split(':', 1)[1].strip()
            elif line.startswith('Control Description:'):
                current_segment['type'] = 'control_description'
                current_segment['text'] = line.split(':', 1)[1].strip()
            elif line.startswith('Test Procedure:'):
                current_segment['type'] = 'test_procedure'
                current_segment['text'] = line.split(':', 1)[1].strip()
            elif line.startswith('Test Result:'):
                current_segment['type'] = 'test_result'
                current_segment['text'] = line.split(':', 1)[1].strip()
        if current_segment:
            segments.append(current_segment)
    except Exception as e:
        logging.error(f'Error parsing classified segments: {e}')
    return segments

# JSON structuring function

def structure_json_records(classified_segments):
    """
    Organize classified segments into structured JSON records.
    """
    json_records = []
    current_record = {}

    for segment in classified_segments:
        segment_type = segment.get('type')
        segment_text = segment.get('text')

        if segment_type == 'control_id':
            if current_record:
                json_records.append(current_record)
                current_record = {}
            current_record['control_id'] = segment_text
        elif segment_type == 'control_description':
            current_record['control_desc'] = segment_text
        elif segment_type == 'test_procedure':
            current_record['control_test'] = segment_text
        elif segment_type == 'test_result':
            current_record['control_test_results'] = segment_text

    if current_record:
        json_records.append(current_record)

    # Log the final json_records for verification
    logging.info("Entering final JSON records logging.")
    logging.info(f"Final JSON records: {json_records}")
    logging.info("Exiting final JSON records logging.")

    return json_records

# Update extract_controls_v2 to use JSON structuring

def extract_controls_v2(file_path):
    """
    Main function to extract controls using the new strategic approach.
    Accepts a file path to the SOC report.
    """
    txt_lines = load_text_lines(file_path)
    section_results = load_json(SECTION_JSON_PATH)
    ctrl_section = find_control_section(section_results)
    if not ctrl_section:
        logging.error('No Control_Descriptions section found.')
        return None

    start_line, end_line = ctrl_section.get('start_line'), ctrl_section.get('end_line')
    text = extract_text_for_lines(txt_lines, start_line, end_line)

    chunks = dynamic_chunking(text)
    logging.info(f'Dynamic chunking produced {len(chunks)} chunks.')

    all_json_records = process_chunks(chunks, txt_lines)

    write_json_output(all_json_records, OUTPUT_JSON_PATH)
    logging.info(f'Control extraction v2 completed. Total controls extracted: {len(all_json_records)}')


def load_text_lines(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.readlines()


def find_control_section(section_results):
    return next((s for s in section_results if s.get("topic") == "Control_Descriptions"), None)


def process_chunks(chunks, txt_lines):
    all_json_records = []
    for idx, chunk in enumerate(chunks):
        logging.info(f'Processing chunk {idx}: {chunk[:200]}...')
        classified_segments = classify_text_segments(chunk)
        json_records = structure_json_records(classified_segments)
        all_json_records.extend(json_records)
    return all_json_records


def write_json_output(data, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'controls': data}, f, ensure_ascii=False, indent=2)


# Simplified process_chunk_with_gpt function

def verify_next_control_start_with_gpt(suggested_start, previous_controls, txt_lines):
    """
    Use GPT to verify if the suggested start of the next control is valid and not a duplicate.
    :param suggested_start: The line number suggested by GPT as the start of the next control.
    :param previous_controls: List of previously identified controls.
    :param txt_lines: The text lines of the document.
    :return: Validated start line or None if invalid.
    """
    # Extract the sentence or context around the suggested start
    context_snippet = txt_lines[suggested_start-1:suggested_start+2]
    context_text = ' '.join(context_snippet).strip()

    # Prepare a prompt for GPT to verify the suggested start
    prompt = (
        f"Verify if the following text is the start of a new control section. "
        f"Ensure it is not a duplicate of any previously identified controls and does not contain test-related language. "
        f"Previously identified controls: {previous_controls}. "
        f"Text to verify: {context_text}"
    )
    logging.info(f"GPT Prompt for verification: {prompt}")
    response = gpt_extract(prompt, 'control_extractor')
    logging.info(f"GPT Response for verification: {response}")

    # Parse the response to determine if the suggested start is valid
    if response and "valid" in response.lower():
        return suggested_start
    else:
        logging.info(f"Suggested start at line {suggested_start} is not valid according to GPT.")
        return None


def process_chunk_with_gpt(chunk, start_line, txt_lines, previous_controls):
    prompt = get_gpt_prompt(chunk, start_line)
    logging.info(f"Processing chunk starting at line {start_line}")
    try:
        response_text = gpt_extract(prompt, 'control_extractor')
        control_data, _, _ = parse_gpt_response(response_text)

        if not control_data.get('control_id') or not control_data.get('control_desc') or not control_data.get('control_test_results'):
            logging.warning("Incomplete control data. Retrying with a larger chunk.")
            return None, start_line, True

        if not is_logically_consistent(control_data):
            logging.warning("Control data is not logically consistent.")
            control_data['unlikely_control'] = True
            return control_data, control_data['end_line'], False

        # Initialize confidence calculation
        control_confidence = control_data.get('control_confidence', 0.5)  # Default to 0.5 if not provided
        confidence_calc = [f"Initial GPT confidence: {control_confidence}"]

        # Store GPT justification for initial confidence
        control_data['control_gpt_conf_justification'] = control_data.get('control_gpt_conf_justification', 'No justification provided')

        # Check for duplicates in control_id and control_desc
        unique_control = True
        for control in previous_controls:
            if control['control_id'] == control_data['control_id'] and control['control_desc'] == control_data['control_desc']:
                control_confidence -= 0.3
                confidence_calc.append("-0.3 for duplicate control_id and control_desc")
                unique_control = False
                break
        if unique_control:
            control_confidence += 0.1
            confidence_calc.append("+0.1 for unique control_id and control_desc")

        # Check if control_id is in additional_references
        if any(control_data['control_id'] in control.get('additional_references', []) for control in previous_controls):
            control_confidence -= 0.1
            confidence_calc.append("-0.1 for control_id in additional_references")

        # Check for key test words in control_desc
        key_test_words = ["examined", "inquired", "ascertained", "inspected", "reviewed"]
        if any(word in control_data['control_desc'] for word in key_test_words):
            control_confidence -= 0.3
            confidence_calc.append("-0.3 for key test words in control_desc")

        # Update control data with confidence information
        control_data['control_confidence'] = round(max(0, min(1, control_confidence)), 1)  # Ensure confidence is between 0 and 1, rounded to 1 decimal place
        control_data['confidence_calc'] = '; '.join(confidence_calc)

        lookahead_start = control_data['end_line']
        lookahead_chunk = extract_text_for_lines(txt_lines, lookahead_start, lookahead_start + 100)

        if len(lookahead_chunk) < 1000:
            logging.warning("Lookahead chunk is shorter than expected.")

        next_control_start = infer_next_control_start(lookahead_chunk, 0)
        logging.info(f"Next control likely starts at line {next_control_start}")

        # Verify the suggested start with GPT
        validated_start = verify_next_control_start_with_gpt(next_control_start, previous_controls, txt_lines)
        if validated_start:
            start_line = lookahead_start + validated_start - 1
        else:
            logging.info("Suggested start was invalid. Searching for next control.")
            # Implement fallback mechanism here if needed
            start_line = control_data['end_line']

        if start_line > 2000:
            logging.info(f"Start line {start_line} exceeds test limit. Stopping processing.")
            return control_data, start_line, False

        logging.info(f"Processed control ending at line {control_data['end_line']}")
        return control_data, control_data['end_line'], False
    except Exception as e:
        logging.error(f"Error calling GPT API: {e}")
        return None, start_line, False

def parse_gpt_response(response_text):
    try:
        # Remove Markdown code block delimiters if present
        if response_text.startswith('```json') and response_text.endswith('```'):
            response_text = response_text[7:-3].strip()

        # Parse the JSON response
        control_data = json.loads(response_text)
        logging.debug(f"Parsed JSON response: {control_data}")
        
        # Extract the line offsets for the control
        lines_into_chunk = control_data.get('start_line', 0)
        lines_covered = control_data.get('end_line', 0)
        return control_data, lines_into_chunk, lines_covered
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON response: {e}")
        return {}, 0, 0

def is_logically_consistent(control_data):
    """
    Checks if the control data is logically consistent.
    For example, ensure that the control description and test results are logically aligned.
    
    :param control_data: The control data to check.
    :return: True if logically consistent, False otherwise.
    """
    # Example logic: Check if control description and test results are aligned
    if "security policy" in control_data.get('control_desc', '').lower() and "background check" in control_data.get('control_test', '').lower():
        return False
    return True

def infer_next_control_start(chunk, current_position):
    # Ensure the chunk is not empty and the current_position is within bounds
    if not chunk or current_position >= len(chunk):
        logging.warning("Chunk is empty or current_position is out of bounds.")
        return None

    # Provide a snippet of text around the current position for context
    snippet_length = 1300  # Increase the size to provide more context
    context_snippet = chunk[current_position:current_position + snippet_length]
    
    # Use GPT to analyze the text and suggest the start of the next control
    prompt = (
        f"Based on the following text, evaluate each full sentence to identify the likely start of the next"
        f" control requirement. Sentences may spread across multiple lines, so evaluate the context of the next"
        f" sentences to determine the likely start of the next control. "
        f"There are no explicit indicators, so infer based on the context of the next sentences. "
        f"There will not be any column headers or other formatting.  It will be a single paragraph or line of text."
        f"Your job is to interpret the text and determine the likely start of the next control.  It will be a "
        f"single paragraph or line of text. May include expressions like 'required to' or 'requires' or 'must' do something."
        f"Don't confuse with a test statement (which may include words like reviewed, evaluated, inspected, inquired, etc.), "
        f"test result, deviation, or other text that may be in the same paragraph or line."
        f"Return just the line number where the next control requirement likely starts. No other text or explanation."
        f"Text snippet: {context_snippet}"
    )
    logging.info(f"GPT Prompt for next control start: {prompt}")  # Log the prompt with context_snippet
    response = gpt_extract(prompt, 'control_extractor')
    logging.info(f"GPT Response for next control start: {response}")
    
    # Parse the response to find the suggested start position
    if response:
        try:
            suggested_start = int(response.strip())
            return suggested_start
        except ValueError:
            logging.warning("Could not parse suggested start position from GPT response.")
    else:
        logging.warning("Received no response for next control start inference.")
    return None

def main():
    # Load section details from JSON
    with open('data/json/section_results.json', 'r', encoding='utf-8') as json_file:
        sections = json.load(json_file)
    
    # Find the Control_Descriptions section
    control_section = next((section for section in sections if section["topic"] == "Control_Descriptions"), None)
    
    if control_section:
        start_line = control_section["start_line"]
        end_line = control_section["end_line"]
    else:
        logging.error("Control_Descriptions section not found in section_results.json")
        return

    file_path = 'data/output/output.txt'
    results = []
    lines_per_chunk = 100

    # Load the text from the specified file
    with open(file_path, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()

    while start_line < end_line:
        retry = False
        for chunk in extract_control_chunks(file_path, start_line, lines_per_chunk=lines_per_chunk):
            try:
                logging.info(f"Processing chunk starting at line {start_line}")
                result, new_start_line, retry = process_chunk_with_gpt(chunk, start_line, txt_lines, results)
                logging.info(f"New Start Line Result: {result}")
                logging.info(f"New Start Line: {new_start_line}")
                if result:
                    results.append(result)
                    start_line = new_start_line
                    logging.info(f"Appended result. Total results: {len(results)}")
                    # Write results incrementally
                    with open('data/output/control_extraction_results.json', 'w', encoding='utf-8') as json_file:
                        json.dump(results, json_file, ensure_ascii=False, indent=4)
                    logging.info("Results written to data/output/control_extraction_results.json")
                    break  # Move to the next chunk after processing one control
                if retry:
                    lines_per_chunk += 25  # Increase chunk size for retry
                    logging.info(f"Retrying with larger chunk size: {lines_per_chunk}")
                    break  # Retry with the same start_line
                if start_line > 2000:
                    logging.info(f"Start line {start_line} exceeds test limit. Stopping processing.")
                    return  # Stop processing when the test limit is reached
            except Exception as e:
                logging.error(f"Error processing chunk: {e}")
                break
        if start_line > 2000:
            logging.info(f"Start line {start_line} exceeds test limit. Stopping processing.")
            break  # Ensure the outer loop also stops

    # Final log of results
    logging.info(f"Final results: {results}")

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_text_for_lines(txt_lines, start_line, end_line):
    """
    Extract text from the specified start to end line numbers.
    """
    return ''.join(txt_lines[start_line-1:end_line])


def get_gpt_prompt(chunk, start_line):
    prompt = f"""
    Your task is to extract detailed control information from the provided text and return it in JSON format. The text is structured in sections, 
    and your focus should be on identifying and extracting specific elements related to a control. Follow the 
    instructions carefully to ensure accurate extraction without inferring any information not explicitly stated in 
    the text.

    Instructions:

    1. Identify Control IDs for a Single Control:
       - Look for one or more control IDs, which may appear as random strings of letters, numbers, periods, dashes, 
       or TSC IDs.
       - Control IDs are unique identifiers for the control and are usually followed by a description.
       - If you find multiple control IDs separated by descriptive text, you should only extract the first set.  The
       next set of IDs will be for either a different control or other references which may be used later for 
       another purpose.

    2. Extract Control Description:
       - Identify and extract 1-5 sentences or a bulleted list that describes the control. Usually follows the control ID.
       - The description should provide a clear understanding of the control's purpose and implementation.

    3. Identify Additional Control References:
       - Look for one or more additional reference strings related to the control, such as series of digits or strings.
       - These references are usually separated by text from the control IDs or control description and may appear 
       in different parts of the text.

    4. Extract Comments on Testing:
       - Identify sentences that describe what was tested, examined, viewed, or reviewed.
       - These comments provide insight into the testing process and methodology.

    5. Extract Test Results:
       - Look for statements indicating test results, such as notes on deviations, findings, gaps, or errors.
       - If no deviations or errors are found, note the absence of such findings.
       - This is usually the last section of the control section.  Anything after this is either not part of the control, 
       is a different control, or is a different section of the report.  Do not include anything after this as it will 
       likely be extracted as part of the next chunk of content being processed.

    6. Provide the Ending Line Number:
       - After extracting the control information, provide the line number where this control information ends.
       - This will be used to determine the starting position for the next chunk.

    7. Provide an Initial Confidence Score and Justification:
       - Provide a confidence score between 0 and 1 indicating how confident you are that the extracted information represents a control.
       - Include a brief justification for your confidence score, explaining why you believe this is a control.

    Return the extracted information in the following JSON format:
    {{
        "control_id": "",
        "control_desc": "",
        "control_test": "",
        "control_test_results": "",
        "additional_references": [],
        "end_line": 0,
        "control_confidence": 0.0,
        "control_gpt_conf_justification": ""
    }}

    Text to analyze (starting at line {start_line}):
    {chunk}
    """
    return prompt


def extract_control_chunks(file_path, start_line, lines_per_chunk=50):
    """
    Extracts chunks of text from a file starting from a specific line.

    :param file_path: Path to the text file.
    :param start_line: Line number to start extraction.
    :param lines_per_chunk: Number of lines per chunk (default is 50).
    :return: Generator yielding chunks of text.
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        # Skip lines until the start line
        for _ in range(start_line - 1):
            next(file)

        # Extract chunks
        while True:
            chunk = ''.join([file.readline() for _ in range(lines_per_chunk)])
            if not chunk.strip():  # Stop if the chunk is empty
                break
            yield chunk

if __name__ == "__main__":
    main() 
import os

def reset_log_file(log_file_path):
    """Reset the log file to keep its size manageable."""
    with open(log_file_path, 'w') as log_file:
        log_file.write('')

# Reset the log file at the start of the extraction process
reset_log_file('data/logs/section_gpt_responses.log') 
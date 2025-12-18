
def reset_log_file(log_file_path):
    """Reset the log file to keep its size manageable."""
    with open(log_file_path, 'w') as log_file:
        log_file.write('')

# Note: Log file reset moved to find_section_candidates() function with job_id parameter 
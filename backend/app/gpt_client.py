import os
import openai
from dotenv import load_dotenv
from app.config import (
    OUTPUT_TEXT_FILE, GPT_PROMPTS, ENV_PATH, DEFAULT_GPT_MODEL, GPT_MODELS,
    DEFAULT_TEMPERATURE, DEFAULT_TOP_P, CHARS_PER_TOKEN, DEFAULT_CHUNK_SIZE, TEXT_OVERLAP
)

def load_api_key():
    load_dotenv(ENV_PATH)
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in .env file.")
    return api_key

def chunk_text(text, chunk_size=DEFAULT_CHUNK_SIZE, overlap=TEXT_OVERLAP):
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunks.append(text[start:end])
        if end == text_length:
            break
        start = end - overlap  # overlap for context
    return chunks

def run_gpt_inquiry(prompt_key, input_file=OUTPUT_TEXT_FILE, model=DEFAULT_GPT_MODEL, temperature=DEFAULT_TEMPERATURE, top_p=DEFAULT_TOP_P):
    api_key = load_api_key()
    openai.api_key = api_key
    if prompt_key not in GPT_PROMPTS:
        raise ValueError(f"Prompt '{prompt_key}' not found in config.")
    with open(input_file, 'r', encoding='utf-8') as f:
        file_text = f.read()
    # Get model-specific chunk size and overlap if available
    model_settings = GPT_MODELS.get(model, {})
    chunk_size = model_settings.get('chunk_size', DEFAULT_CHUNK_SIZE)
    overlap = model_settings.get('overlap', TEXT_OVERLAP)
    chunks = chunk_text(file_text, chunk_size, overlap)
    prompt_template = GPT_PROMPTS[prompt_key]
    responses = []
    for i, chunk in enumerate(chunks):
        prompt = f"{prompt_template}\n\nReport Text (part {i+1}/{len(chunks)}):\n{chunk}"
        response = openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            top_p=top_p
        )
        responses.append(response.choices[0].message.content)
    return "\n\n---\n\n".join(responses)

def gpt_extract(prompt, model=DEFAULT_GPT_MODEL, temperature=DEFAULT_TEMPERATURE, top_p=DEFAULT_TOP_P):
    api_key = load_api_key()
    openai.api_key = api_key
    response = openai.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        top_p=top_p
    )
    return response.choices[0].message.content

def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Run GPT inquiry on SOC 2 report text.")
    parser.add_argument('--prompt', type=str, help='Prompt key to use (see config.py)')
    parser.add_argument('--input', type=str, default=OUTPUT_TEXT_FILE, help='Input text file (default: output.txt)')
    parser.add_argument('--model', type=str, default=DEFAULT_GPT_MODEL, help='GPT model to use (see config.py)')
    parser.add_argument('--temperature', type=float, default=DEFAULT_TEMPERATURE, help='Sampling temperature')
    parser.add_argument('--top_p', type=float, default=DEFAULT_TOP_P, help='Nucleus sampling top_p')
    parser.add_argument('--analyze', action='store_true', help='Analyze SOC 2 report and estimate section positions')
    parser.add_argument('--section-candidates', action='store_true', help='Find section candidates with probability/confidence approach')
    parser.add_argument('--json', type=str, default='data/json/section_candidates.json', help='Output JSON file for section candidates')
    args = parser.parse_args()

    if args.section_candidates:
        from pdf_handler import find_section_candidates
        with open(args.input, 'r', encoding='utf-8') as f:
            text = f.read()
        print("Finding section candidates with probability/confidence approach...")
        results = find_section_candidates(text, args.model, args.temperature, args.top_p)
        for topic, candidates in results.items():
            print(f"\nSection: {topic}")
            for cand in candidates:
                print(f"  Offset: {cand['offset']} | Confidence: {cand['confidence']} | Indicators: {cand['indicators']}\n  Snippet: {cand['snippet'][:200]}\n---")
        # Save to JSON file
        os.makedirs(os.path.dirname(args.json), exist_ok=True)
        with open(args.json, 'w', encoding='utf-8') as jf:
            json.dump(results, jf, indent=2)
        print(f"Section candidate results saved to {args.json}")
    elif args.analyze:
        from pdf_handler import get_section_positions
        with open(args.input, 'r', encoding='utf-8') as f:
            text = f.read()
        total_chars = len(text)
        print(f"Total character count: {total_chars}")
        result = get_section_positions(text, args.model, args.temperature, args.top_p)
        print("\nSection positions and confidence:")
        print(result)
    else:
        if not args.prompt:
            raise ValueError("Prompt key is required unless --analyze or --section-candidates is used.")
        result = run_gpt_inquiry(args.prompt, args.input, args.model, args.temperature, args.top_p)
        print("\nGPT Response:\n", result)

if __name__ == "__main__":
    main()

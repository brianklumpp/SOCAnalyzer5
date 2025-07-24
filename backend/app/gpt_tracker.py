"""
GPT Usage Tracker - Centralized tracking of GPT API usage, costs, and timing
"""
import time
import threading
from typing import Dict, List, Optional
from collections import defaultdict

class GPTUsageTracker:
    """Thread-safe tracker for GPT usage across all extractors"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._usage_data: List[Dict] = []
        self._models_used: set = set()
        self._total_cost: float = 0.0
        self._total_calls: int = 0
        
        # OpenAI pricing (as of 2024) - tokens per dollar
        self._model_pricing = {
            'gpt-4o': {'input': 0.0025 / 1000, 'output': 0.01 / 1000},  # $2.50/$10.00 per 1M tokens
            'gpt-4': {'input': 0.03 / 1000, 'output': 0.06 / 1000},     # $30/$60 per 1M tokens
            'gpt-3.5-turbo': {'input': 0.0005 / 1000, 'output': 0.0015 / 1000}  # $0.50/$1.50 per 1M tokens
        }
    
    def track_gpt_call(self, model: str, prompt_tokens: int, completion_tokens: int, 
                      extractor_name: str, duration_seconds: float) -> Dict:
        """Track a single GPT API call"""
        with self._lock:
            # Calculate cost
            pricing = self._model_pricing.get(model, self._model_pricing['gpt-3.5-turbo'])
            input_cost = prompt_tokens * pricing['input']
            output_cost = completion_tokens * pricing['output']
            total_cost = input_cost + output_cost
            
            # Record usage
            usage_record = {
                'model': model,
                'extractor': extractor_name,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': prompt_tokens + completion_tokens,
                'cost': total_cost,
                'duration_seconds': duration_seconds,
                'timestamp': time.time()
            }
            
            self._usage_data.append(usage_record)
            self._models_used.add(model)
            self._total_cost += total_cost
            self._total_calls += 1
            
            return usage_record
    
    def get_summary(self) -> Dict:
        """Get summary of all GPT usage"""
        with self._lock:
            if not self._usage_data:
                return {
                    'gpt_cost': 0.0,
                    'gpt_model': [],
                    'gpt_usage_details': [],
                    'total_calls': 0,
                    'total_tokens': 0
                }
            
            # Aggregate by model
            by_model = defaultdict(lambda: {'calls': 0, 'cost': 0.0, 'tokens': 0})
            for record in self._usage_data:
                model = record['model']
                by_model[model]['calls'] += 1
                by_model[model]['cost'] += record['cost']
                by_model[model]['tokens'] += record['total_tokens']
            
            # Create summary
            model_list = [f"{model} ({data['calls']} calls)" for model, data in by_model.items()]
            total_tokens = sum(record['total_tokens'] for record in self._usage_data)
            
            return {
                'gpt_cost': round(self._total_cost, 4),
                'gpt_model': ', '.join(model_list),
                'gpt_usage_details': self._usage_data.copy(),
                'total_calls': self._total_calls,
                'total_tokens': total_tokens,
                'by_model': dict(by_model)
            }
    
    def reset(self):
        """Reset all tracking data"""
        with self._lock:
            self._usage_data.clear()
            self._models_used.clear()
            self._total_cost = 0.0
            self._total_calls = 0

# Global tracker instance
_global_tracker = GPTUsageTracker()

def get_tracker() -> GPTUsageTracker:
    """Get the global GPT usage tracker"""
    return _global_tracker

def track_gpt_call(model: str, prompt_tokens: int, completion_tokens: int, 
                  extractor_name: str, duration_seconds: float) -> Dict:
    """Convenience function to track a GPT call"""
    return _global_tracker.track_gpt_call(model, prompt_tokens, completion_tokens, 
                                         extractor_name, duration_seconds)

def get_usage_summary() -> Dict:
    """Convenience function to get usage summary"""
    return _global_tracker.get_summary()

def reset_tracking():
    """Convenience function to reset tracking"""
    _global_tracker.reset() 
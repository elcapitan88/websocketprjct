import os
import psutil
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def get_system_metrics() -> Dict[str, Any]:
    """
    Get system resource metrics
    
    Returns:
        Dictionary containing system resource metrics
    """
    try:
        # Get current process
        process = psutil.Process(os.getpid())
        
        # Get CPU usage
        cpu_percent = process.cpu_percent(interval=0.1)
        
        # Get memory usage
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()
        
        # Get open files and connections count
        try:
            open_files = len(process.open_files())
        except Exception:
            open_files = -1
            
        try:
            connections = len(process.connections())
        except Exception:
            connections = -1
        
        # Get number of threads
        thread_count = process.num_threads()
        
        # Get system load average
        try:
            load_avg = os.getloadavg()
        except (AttributeError, OSError):
            # Not available on Windows
            load_avg = (-1, -1, -1)
        
        # Get system memory info
        system_memory = psutil.virtual_memory()
        
        return {
            "process": {
                "cpu_percent": round(cpu_percent, 2),
                "memory_mb": round(memory_info.rss / (1024 * 1024), 2),
                "memory_percent": round(memory_percent, 2),
                "open_files": open_files,
                "connections": connections,
                "thread_count": thread_count
            },
            "system": {
                "load_avg_1min": round(load_avg[0], 2),
                "load_avg_5min": round(load_avg[1], 2),
                "load_avg_15min": round(load_avg[2], 2),
                "memory_total_mb": round(system_memory.total / (1024 * 1024), 2),
                "memory_available_mb": round(system_memory.available / (1024 * 1024), 2),
                "memory_percent": round(system_memory.percent, 2)
            }
        }
    except Exception as e:
        logger.error(f"Error getting system metrics: {str(e)}")
        return {
            "error": str(e)
        }
"""
Parallel executor utilities for concurrent OCI API operations.
Copyright (c) 2025 Oracle and/or its affiliates.
"""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from .progress import ProgressTracker


class OCIMetadataFetcher:
    """Fetch OCI instance metadata in parallel using ThreadPoolExecutor."""
    
    def __init__(self, max_workers=10):
        """Initialize fetcher with thread pool size."""
        self.max_workers = max_workers
    
    def _fetch_single_instance(self, instance_id):
        """Fetch metadata for a single instance. Helper for parallel processing."""
        try:
            # Extract region from OCID (format: ocid1.instance.oc1.<region>.<unique_id>)
            parts = instance_id.split('.')
            if len(parts) < 4:
                return instance_id, None
            
            region = parts[3]
            
            # Call OCI CLI to get instance details
            result = subprocess.run(
                [
                    'oci', 'compute', 'instance', 'get',
                    '--instance-id', instance_id,
                    '--region', region,
                    '--output', 'json'
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                instance_data = json.loads(result.stdout)
                if 'data' in instance_data:
                    data = instance_data['data']
                    return instance_id, {
                        'shape': data.get('shape', ''),
                        'resourceName': data.get('display-name', '')
                    }
            
            return instance_id, None
        
        except subprocess.TimeoutExpired:
            return instance_id, None
    
    def fetch_metadata(self, instance_ids, progress_callback=None):
        """
        Fetch metadata for multiple instances in parallel with progress tracking.
        
        Args:
            instance_ids: List of instance OCIDs
            progress_callback: Optional callback function to update progress (takes current_count)
        
        Returns:
            Tuple of (instance_metadata dict, successful count, failed count)
        """
        instance_metadata = {}
        successful = 0
        failed = 0
        completed = 0
        
        # Create progress tracker
        progress = ProgressTracker(len(instance_ids), "Retrieving instance details")
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_instance = {
                executor.submit(self._fetch_single_instance, iid): iid 
                for iid in instance_ids
            }
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_instance):
                instance_id, metadata = future.result()
                completed += 1
                
                if metadata is not None:
                    instance_metadata[instance_id] = metadata
                    successful += 1
                else:
                    failed += 1
                
                # Update progress display
                progress.update(completed)
                
                # Optional callback
                if progress_callback:
                    progress_callback(completed)
        
        # Finish progress display
        progress.finish()
        
        return instance_metadata, successful, failed

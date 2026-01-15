# create_indexer.py
from azure.search.documents.indexes import SearchIndexerClient
from azure.search.documents.indexes.models import (
    SearchIndexer, 
    SearchIndexerDataSourceConnection, 
    SearchIndexerDataContainer,
    FieldMapping
)
from azure.core.credentials import AzureKeyCredential

# Initialize the indexer client
client = SearchIndexerClient(
    endpoint="https://grams-analyticsai-openai-dev.openai.azure.com/",
    credential=AzureKeyCredential("EFOnddeert8cgwog9dncbhuysferrtadbCY")
)

# Step 1: Create or update the data source
print("Creating data source...")
data_source = SearchIndexerDataSourceConnection(
    name="grams-blob-datasource",
    type="azureblob",
    connection_string="DefaultEndpointsProtocol=https;AccountName=grams;AccountKey=FDMqfToWsvpZM4/o5Q3d9dghhjj+kkjhuokbssdffsdmZk1IUs3gsvcp/V9Zi9Z06Qwn27+AStGQbwFw==;EndpointSuffix=core.windows.net",
    container=SearchIndexerDataContainer(name="gramsanalyticsknowledge01")
)

try:
    client.create_or_update_data_source_connection(data_source)
    print("✓ Data source created/updated")
except Exception as e:
    print(f"✗ Data source error: {e}")

# Step 2: Create the indexer
print("Creating indexer...")
indexer = SearchIndexer(
    name="grams-blob-indexer",
    data_source_name="grams-blob-datasource",
    target_index_name="grams-analytics-search-index",
    field_mappings=[
        FieldMapping(source_field_name="metadata_storage_path", target_field_name="url"),
        FieldMapping(source_field_name="metadata_storage_name", target_field_name="title"),
        FieldMapping(source_field_name="content", target_field_name="content")
    ]
)

try:
    client.create_or_update_indexer(indexer)
    print("✓ Indexer created/updated")
    
    # Run the indexer immediately
    print("Running indexer...")
    client.run_indexer("grams-blob-indexer")
    print("✓ Indexer started - it will sync your blob storage with the search index")
    
    # Check indexer status
    status = client.get_indexer_status("grams-blob-indexer")
    print(f"Indexer status: {status.status}")
    print(f"Last run: {status.last_result.status if status.last_result else 'Not run yet'}")
    
except Exception as e:
    print(f"✗ Indexer error: {e}")
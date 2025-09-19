import json
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upload_rss_feeds(rss_feeds, table_name):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)

    logger.info(f"Uploading RSS feeds to table: {table_name}")

    try:
        # Get the table's key schema
        key_schema = table.key_schema
        partition_key = next(key['AttributeName'] for key in key_schema if key['KeyType'] == 'HASH')
    except ClientError as e:
        logger.error(f"Error getting table schema: {e.response['Error']['Message']}")
        return

    new_items = 0
    updated_items = 0

    for feed in rss_feeds:
        feed_url = feed.get('u')
        if not feed_url:
            logger.warning(f"Skipping feed with no 'u' (url) field: {feed}")
            continue

        # Check if the item already exists
        try:
            response = table.get_item(Key={partition_key: feed_url})
        except ClientError as e:
            logger.error(f"Error checking for existing item: {e.response['Error']['Message']}")
            continue

        if 'Item' not in response:
            item = {partition_key: feed_url}
            try:
                item['dt'] = int(feed.get('dt', 0))
            except (TypeError, ValueError):
                item['dt'] = 0

            for k, v in feed.items():
                if k == 'u' or k == 'dt':
                    continue
                item[k] = v

            try:
                table.put_item(Item=item)
                new_items += 1
            except ClientError as e:
                logger.error(f"Error inserting new item: {e.response['Error']['Message']}")
        else:
            update_expr_parts = []
            expr_attr_vals = {}
            try:
                # Always update dt if provided
                if 'dt' in feed:
                    update_expr_parts.append('#dt = :d')
                    expr_attr_vals[':d'] = int(feed.get('dt', 0))
                    expr_attr_names = {'#dt': 'dt'}
                else:
                    expr_attr_names = {}

                for k, v in feed.items():
                    if k == 'u' or k == 'dt':
                        continue
                    placeholder = f':{k}'
                    name_placeholder = f'#_{k}'
                    update_expr_parts.append(f"{name_placeholder} = {placeholder}")
                    expr_attr_vals[placeholder] = v
                    expr_attr_names[name_placeholder] = k

                if update_expr_parts:
                    update_expression = 'SET ' + ', '.join(update_expr_parts)
                    expression_attribute_values = {k: v for k, v in expr_attr_vals.items()}

                    table.update_item(
                        Key={partition_key: feed_url},
                        UpdateExpression=update_expression,
                        ExpressionAttributeNames=expr_attr_names if expr_attr_names else None,
                        ExpressionAttributeValues=expression_attribute_values
                    )
                    updated_items += 1
                else:
                    pass
            except ClientError as e:
                logger.error(f"Error updating existing item: {e.response['Error']['Message']}")

    logger.info(f"Upload complete. {new_items} new items inserted. {updated_items} items updated or already existed.")

if __name__ == "__main__":
    table_name = 'rss-feeds-table'
    rss_feed_path = 'rss_feeds.json'
    with open(rss_feed_path) as f:
        rss_feeds = json.load(f)
    logger.info(f"Loaded RSS feeds: {rss_feeds}")
    upload_rss_feeds(rss_feeds, table_name)
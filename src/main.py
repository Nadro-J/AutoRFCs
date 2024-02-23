import os
import time
import json
import logging
import requests
import deepdiff
from typing import Dict, Any
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session


class TwitterAuth(OAuth1Session):
    def __init__(self, consumer_key, consumer_secret, token, token_secret):
        super(TwitterAuth, self).__init__(consumer_key, consumer_secret, resource_owner_key=token, resource_owner_secret=token_secret)


class CacheManager:
    @staticmethod
    def save_data_to_cache(filename: str, data: Dict[str, Any]) -> None:
        """Save data to a JSON file."""
        with open(filename, 'w') as cache:
            json.dump(data, cache, indent=4)

    @staticmethod
    def load_data_from_cache(filename: str) -> Dict[str, Any]:
        """Load data from a JSON file."""
        with open(filename, 'r') as cache:
            cached_file = json.load(cache)
        return cached_file

    @staticmethod
    def get_cache_difference(filename: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Compare the provided data with the cached data and return the difference using deepdiff."""
        full_path = os.path.join("", filename)

        if not os.path.isfile(full_path):
            CacheManager.save_data_to_cache(full_path, data)
            return {}

        cached_data = CacheManager.load_data_from_cache(full_path)

        # use DeepDiff to check if any values have changed since we ran has_commission_updated().
        difference = deepdiff.DeepDiff(cached_data, data, ignore_order=True).to_json()
        result = json.loads(difference)
        if len(result) == 0:
            return {}
        else:
            return result


def post_tweet(text, consumer_key, consumer_secret, access_token, access_token_secret):
    try:
        logging.info("Composing tweet, please wait...")
        url = "https://api.twitter.com/2/tweets"
        twitter = TwitterAuth(consumer_key, consumer_secret, access_token, access_token_secret)
        payload = json.dumps({"text": text})
        headers = {'Content-Type': 'application/json'}
        response = twitter.post(url, headers=headers, data=payload)
        logging.info("Executed tweet")
        return response.text
    except ValueError as e:
        logging.error(f"Invalid data input: {e}")
        return None
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return None


def pull_requests(owner, repo):
    """
    Fetch open pull requests from a github repository.

    Parameters:
    - owner: The username of the repo owner.
    - repo: The name of the repo.

    Returns:
    Fetch a list of all open PRs
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    params = {'state': 'open'}
    response = requests.get(url, params=params)
    logging.info(f"Pulling PRs from {url}, please wait...")

    if response.status_code == 200:
        pull_requests = response.json()
        prs = {}

        for pr in pull_requests:
            prs[pr['id']] = {
                'title': pr['title'],
                'number': pr['number'],
                'url': pr['_links']['html']['href'],
                'author': pr['user']['html_url'],
                'created_at': pr['created_at']
            }
        return json.loads(json.dumps(prs, sort_keys=True))
    else:
        logging.error(f"Failed to fetch pull requests: {response.status_code}")
        return None


def check_for_new_pr():
    logging.info("Checking for new RFC(s)")

    pull_request_info = pull_requests(os.environ['REPO_OWNER'], os.environ['REPO'])
    result = CacheManager.get_cache_difference(filename='../data/pull_requests.json', data=pull_request_info)
    CacheManager.save_data_to_cache(filename='../data/pull_requests.json', data=pull_request_info)

    if result:
        for key, value in result.items():
            if 'added' in key:
                logging.info(f"{len(result['dictionary_item_added'])} new RFC(s)! Parsing data, please wait...")
                for index in result['dictionary_item_added']:
                    index = index.strip('root').replace("['", "").replace("']", "")
                    data = pull_request_info[index]
                    logging.info(f"Crafting tweet for RFC #{data['number']}")
                    tweet = f"""
A new @Polkadot RFC has been raised! #RFC{data['number']} #Polkadot

Title: {data['title']}
Author: {data['author']}

{data['url']}
                    """
                    post_tweet(text=tweet,
                               consumer_key=os.environ['CONSUMER_KEY'],
                               consumer_secret=os.environ['CONSUMER_SECRET'],
                               access_token=os.environ['ACCESS_TOKEN'],
                               access_token_secret=os.environ['ACCESS_TOKEN_SECRET'])
                    time.sleep(10)  # mitigate throttling by placing a 50s gap inbetween each tweet


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers = [
                            logging.FileHandler('../logs/app.log'),
                            logging.StreamHandler()]
                        )
    load_dotenv()
    check_for_new_pr()
    logging.info("Finished")

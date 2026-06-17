import os
import base64
import logging
import requests
from core import settings
from cachetools import TTLCache

logger = logging.getLogger(__name__)

token_cache = TTLCache(maxsize=1, ttl=43200)  # 12hours


def get_api_token_cached() -> str:
    """Get API token with caching"""

    if 'token' in token_cache:
        logger.info("Using cached API token")
        return token_cache['token']

    try:
        data = {
            "userCode": settings.QIWEI_PUSH_API_LOGIN_USERCODE,
            "password": settings.QIWEI_PUSH_API_LOGIN_PASSWORD
        }

        response = requests.post(settings.QIWEI_PUSH_API_URL+"/login", json=data)
        if response.status_code == 200:
            result = response.json()
            token = result.get("data", {}).get("token", "")
            if token:
                token_cache['token'] = token
                logger.info("API token retrieved and cached successfully")
                return token
    except Exception as e:
        logger.error(f"Failed to get API token: {e}")
    return ""


async def uploadFile(file_path: str, api_token: str) -> str:
    """
    Upload a file to get mediaId.

    Args:
        file_path: Path to the local file to upload
        api_token: API token for authentication

    Returns:
        mediaId: The media ID returned by the API

    Raises:
        FileNotFoundError: If the file does not exist
        requests.RequestException: If there's an error in the API request
        KeyError: If mediaId is not found in the response
    """
    try:
        # Read the file content and encode it as base64
        with open(file_path, 'rb') as f:
            file_content = f.read()
            file_byte = base64.b64encode(file_content).decode('utf-8')

        # Prepare the request body
        file_name = os.path.basename(file_path)
        payload = {
            "agentId": settings.QIWEI_PUSH_API_SENDTEXT_AGENTID,
            "msgtype": "file",
            "file": {
                "fileName": file_name,
                "fileByte": file_byte
            }
        }

        # Prepare headers
        headers = {
            'Content-Type': 'application/json',
            'Token': api_token
        }

        # Make the API request
        url = settings.QIWEI_PUSH_API_URL + "/weChatNotice/getMediaId"
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors

        # Parse the response and return mediaId
        result = response.json()
        media_id = result.get("mediaId")
        if not media_id:
            raise KeyError("mediaId not found in response")

        logger.info(f"File uploaded successfully, mediaId: {media_id}")
        return media_id

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        raise
    except KeyError as e:
        logger.error(f"Response parsing failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in uploadFile: {e}")
        raise


async def sendFile(users: list, media_id: str, api_token: str) -> dict:
    """
    Send a file to a list of users using mediaId.

    Args:
        users: List of user IDs to send the file to
        media_id: The media ID obtained from uploadFile
        api_token: API token for authentication

    Returns:
        dict: The response from the API

    Raises:
        requests.RequestException: If there's an error in the API request
        ValueError: If users list is empty or media_id is empty
    """
    try:
        # Check if file sending is enabled
        if not settings.SEND_FILE_FLAG:
            logger.info("File sending is disabled by SEND_FILE_FLAG")
            return {}
        
        # Validate input
        if not users:
            raise ValueError("Users list cannot be empty")
        if not media_id:
            raise ValueError("media_id cannot be empty")

        # Prepare the request body
        touser = "|".join(users)
        payload = {
            "touser": touser,
            "agentId": settings.QIWEI_PUSH_API_SENDTEXT_AGENTID,
            "msgtype": "file",
            "mediaId": media_id
        }

        # Prepare headers
        headers = {
            'Content-Type': 'application/json',
            'Token': api_token
        }

        # Make the API request
        url = settings.QIWEI_PUSH_API_URL + "/weChatNotice/sendFile"
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors

        # Parse and return the response
        result = response.json()
        logger.info(f"File sent successfully to {len(users)} users")
        return result

    except ValueError as e:
        logger.error(f"Input validation failed: {e}")
        raise
    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in sendFile: {e}")
        raise

async def push_wechat_text(users: set, content: str, api_token: str) -> dict:
    """
    Push text/markdown message to WeChat
    
    Args:
        users: Set of user IDs to send the message to
        content: The content of the message
        api_token: API token for authentication
    
    Returns:
        dict: The response from the API
    
    Raises:
        requests.RequestException: If there's an error in the API request
        ValueError: If users set is empty or content is empty
    """
    try:
        # Check if text sending is enabled
        if not settings.SEND_FILE_FLAG:
            logger.info("Text sending is disabled by SEND_FILE_FLAG")
            return {}
        
        # Validate input
        if not users:
            raise ValueError("Users set cannot be empty")
        if not content:
            raise ValueError("Content cannot be empty")

        # Prepare the request body
        data = {
            "touser": "|".join(users),
            "agentId": settings.QIWEI_PUSH_API_SENDTEXT_AGENTID,
            "content": content
        }

        # Prepare headers
        headers = {
            'Content-Type': 'application/json',
            'Token': api_token
        }

        # Make the API request
        response = requests.post(settings.QIWEI_PUSH_API_URL+"/weChatNotice/sendMarkdown", headers=headers, json=data)
        response.raise_for_status()  # Raise exception for HTTP errors

        # Parse and return the response
        result = response.json()
        logger.info(f"Text report pushed successfully to {len(users)} users")
        return result

    except ValueError as e:
        logger.error(f"Input validation failed: {e}")
        raise
    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in push_wechat_text: {e}")
        raise
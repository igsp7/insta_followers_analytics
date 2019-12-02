from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup
import boto3
from boto3.dynamodb.conditions import Attr, Key
import concurrent.futures
import inspect
import json
import logging
import os
import random
import sys
import time

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1280x1696')
chrome_options.add_argument('--user-data-dir=/tmp/user-data')
chrome_options.add_argument('--hide-scrollbars')
chrome_options.add_argument('--enable-logging')
chrome_options.add_argument('--log-level=0')
chrome_options.add_argument('--v=99')
chrome_options.add_argument('--single-process')
chrome_options.add_argument('--data-path=/tmp/data-path')
chrome_options.add_argument('--ignore-certificate-errors')
chrome_options.add_argument('--homedir=/tmp')
chrome_options.add_argument('--disk-cache-dir=/tmp/cache-dir')
chrome_options.add_argument('user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36')
chrome_options.binary_location = os.getcwd() + "/bin/headless-chromium"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class FailedLoginError(Error):
    """Exception raised when the login to instagram fails"""
    pass

class FailedGettingUsersCountError(Error):
    """Exception raised when failling to get users count"""
    pass

class FailedGettingUsersError(Error):
    """Exception raised when failling to get users list"""
    pass

VALID_USERS_TYPE_ = {'followers', 'following'}
 
def lambda_handler(event, context):
    if not event: # empty dicts evaluate to False 
        # default values if nothing is passed
        event = {
            "username": "agoodusernameisnotenough",
            "password": "test1234",
            "user_id": "didima_feggaria",
            "login_retries": 3,
            "get_users_retries": 3,
            "users_type": "followers",
            "location": "skg"
        }

    try:
        users_list = getUsers(event)[1]

        dynamodb = boto3.resource('dynamodb', region_name='eu-central-1')
        users_table = dynamodb.Table(event["users_type"])
        deleted_users_table = dynamodb.Table('deleted_' + event['users_type'])

        #geting the users who belong to the given user_id
        response = users_table.scan(
            FilterExpression=Attr('belongs_to').eq(event['user_id'])
        )

        old_users = response['Items']
        old_users_ids = [old_user["ig_id"] for old_user in old_users]

        updated_users_set = set(users_list)
        deleted_users = [old_user for old_user in old_users if old_user["ig_id"] not in updated_users_set]
        
        old_users_ids_set = set(old_users_ids)
        new_users = [user_id for user_id in users_list if user_id not in old_users_ids_set]

        for deleted_user in deleted_users:
            users_table.delete_item(
                Key = {
                    "ig_id": deleted_user["ig_id"],
                    "followed_date": deleted_user["followed_date"]
                }
            )

            deleted_users_table.put_item(
                Item = deleted_user
            )
        
        current_time = int(time.time())

        users_table_item_dict = {
            "belongs_to": event["user_id"]
        }
        if 'hashtag' in event:
            users_table_item_dict.update(hashtag = event["hashtag"])

        if 'location' in event:
            users_table_item_dict.update(location = event["location"])

        for new_user in new_users:
                users_table_item_dict.update([
                    ("ig_id", new_user),
                    ("followed_date", current_time)
                ])
                users_table.put_item(
                    Item = users_table_item_dict
                )
                current_time -= 1

    except Exception as exc:
        return {
            'statusCode': '500',
            'body': json.dumps(repr(exc))
        }

    return_body = {
        f'new_{event["user_type"]}_count': len(new_users),
        f'deleted_{event["user_type"]}_count': len(new_users)
    }
    return {
        'statusCode': 200,
        'body': json.dumps(return_body)
    }

def login(driver, hyperparameters, reloging = False):
    if(reloging == False):
        driver.get('https://www.instagram.com/accounts/login/?next=/explore/')
        time.sleep(2)
    try:
        logger.info('Trying to log in...\n')
        write_username = driver.find_element_by_xpath('//html/body/span/section/main/div/article/div/div[1]/div/form/div[2]/div/label/input')
        write_username.send_keys(hyperparameters['username'])
        write_password = driver.find_element_by_xpath('/html/body/span/section/main/div/article/div/div[1]/div/form/div[3]/div/label/input')
        write_password.send_keys(hyperparameters['password'])
        write_password.send_keys(Keys.ENTER)
        time.sleep(2)
    except NoSuchElementException as exc:
        logger.info(exc)
        logger.info('Already logged in!\n')
    finally:
        if(driver.current_url != 'https://www.instagram.com/explore/'):
            raise FailedLoginError
        
        logger.info('Successfull login')
        logger.info(f'Redirecting to {hyperparameters["user_id"]}\'s page...\n')
        driver.get('https://www.instagram.com/' + hyperparameters['user_id'])
        time.sleep(2)

def getUsersCount(driver, target):
    if target == 'followers':
        users_count=int(driver.find_element_by_xpath("//li[2]/a/span").text) 
    else:
        users_count=int(driver.find_element_by_xpath("//li[3]/a/span").text) 
    
    return users_count

def getUsersList(driver, users_count, type_):
    checkUsersType_(type_)
    #find users count in user page and click
    if type_ == "followers":
        users_count_button = driver.find_element_by_xpath('/html/body/span/section/main/div/header/section/ul/li[2]/a')
    else:
        users_count_button = driver.find_element_by_xpath('/html/body/span/section/main/div/header/section/ul/li[3]/a')

    users_count_button.click()
    #wait for users modal to pop up
    time.sleep(1)

    #find followers pop up
    dialog = driver.find_element_by_xpath('/html/body/div[3]/div/div[2]')
    time.sleep(1)

    #scroll once for a random ammount to prevent going to suggestions
    driver.execute_script("arguments[0].scrollTop = 300", dialog)

    #scroll through followers to go to the end of the list 
    logger.info('Scrolling through followers\' scroll box:')
    for i in range(int(users_count / 11)): #it is divided by 11 because each iteration scrolls through 11 users
        time.sleep(random.randint(500,1000)/1000)
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", dialog)

    page_source = driver.page_source
    dom_BS=BeautifulSoup(page_source, "html.parser") #BS stands for Beautiful Soup !!!

    users_list = []

    users_divs_BS = dom_BS.find_all("div", class_="d7ByH")

    for user_div_BS in users_divs_BS:
        for a in user_div_BS.find_all('a', href = True):
            users_list.append(a['href'][1:-1]) #Getting rid of the slash at the start and the end of the instagram id 

    if(len(users_list) != users_count):
        raise FailedGettingUsersError('Number of actual users is not equal to the number of found users')
    
    return users_list

def getUsers(hyperparameters):
    type_ = hyperparameters["users_type"]
    checkUsersType_(type_) 
    logger.info('Getting users')
    driver = webdriver.Chrome(chrome_options=chrome_options)
    
    reloging = False
    failed_attemps = 0

    while failed_attemps < hyperparameters['login_retries']:
        try:
            login(driver, hyperparameters, reloging)
        except FailedLoginError:
            logger.info('Login failled!\n')
            reloging = True
            failed_attemps += 1
        else: 
            break
    
    if failed_attemps == hyperparameters['login_retries']:
        driver.close()
        raise FailedLoginError('Login failed on all retries!\n')
            
 
    try:
        users_count = getUsersCount(driver, type_)
    except NoSuchElementException: 
        logger.info('Tryging to get users count while not at user\'s page')
        logger.info(f'Redirecting to {hyperparameters["user_id"]}\'s page...\n')
        driver.get('https://www.instagram.com/' + hyperparameters['user_id'])
        time.sleep(2)
        users_count = getUsersCount(driver, type_)
        
        
    failed_attemps = 0

    while failed_attemps < hyperparameters['get_users_retries']:
        try:
            users_list = getUsersList(driver, users_count, type_)
        except Exception as exc:
            logger.info('Failed getting users!\n')
            logger.info(exc)
            try:
                close_modal_button = driver.find_element_by_xpath('/html/body/div[3]/div/div[1]/div/div[2]/button')
                close_modal_button.click()
            except:
                pass

            failed_attemps += 1
        else: 
            break

    if failed_attemps == hyperparameters['get_users_retries']:
        driver.close()
        raise FailedGettingUsersError('Failed getting users after all retries')


    driver.close()
    return users_count, users_list

def checkUsersType_(type_):
    if type_ not in VALID_USERS_TYPE_:
        curframe = inspect.currentframe()
        calframe = inspect.getouterframes(curframe, 2)
        caller_name = calframe[1][3]
        raise ValueError(f'{caller_name}: type_ must be either followers or following') #get the caller function's name and raise an error
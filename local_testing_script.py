from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup
import boto3
from boto3.dynamodb.conditions import Attr, Key
import concurrent.futures
import inspect
import logging
import random
import sys
import time
import threading

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] (%(threadName)-9s) %(message)s',)
VALID_USERS_TYPE_ = {'followers', 'following'}

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


def main():
    event = {
        "username": "agoodusernameisnotenough",
        "password": "test1234",
        "user_id": "didima_feggaria",
        "login_retries": 3,
        "get_users_retries": 3,
        "users_type": "followers",
        "location": "skg"
    }
    with concurrent.futures.ThreadPoolExecutor(thread_name_prefix="Thread") as executor:
        future_followers = executor.submit(getUsers, event)
        # future_following = executor.submit(getUsers,'following', hyperparameters)
        try:

            t1 = time.perf_counter()
            users_list = []
            following_list = []
            actual_users_count =  future_followers.result()[0]
            found_users_count = len(future_followers.result()[1])
            users_list = future_followers.result()[1]

            dynamodb = boto3.resource('dynamodb', region_name='eu-central-1')
            users_table = dynamodb.Table('followers')
            deleted_users_table = dynamodb.Table('deleted_' + event['users_type'])

            response = users_table.scan(
                FilterExpression=Attr('belongs_to').eq(event['user_id'])
            )

            old_users = response['Items']
            old_users_ids = []


            for old_user in old_users:
                old_users_ids.append(old_user["ig_id"])

            updated_users_set = set(users_list)
            deleted_users = [old_user for old_user in old_users if old_user["ig_id"] not in updated_users_set]

            s = set(old_users_ids)
            new_users = [x for x in users_list if x not in s]


            for deleted_user in deleted_users:
                print(deleted_user)
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


                


            
            

            # print('Actual number of following:' + str(future_following.result()[0]))
            # print('Number of found following:' + str(len(future_following.result()[1])))
            # following_list.append(future_following.result()[1])
            # s = set(users_list[0])
            # not_followers = [x for x in following_list[0] if x not in s]

            # print('Count of not followers: ' + str(len(not_followers)))
            # print(not_followers)
            t2 = time.perf_counter()
            logging.info(future_followers.result())

            
            # for item in 
            logging.info(f'Finished in {t2 - t1}')

        except Exception as exc:
            logging.info('generated an exception: %s' % (exc))

def login(driver, hyperparameters, reloging = False):
    if(reloging == False):
        driver.get('https://www.instagram.com/accounts/login/?next=/explore/')
        time.sleep(2)
    try:
        logging.info('Trying to log in...\n')
        write_username = driver.find_element_by_xpath('//html/body/span/section/main/div/article/div/div[1]/div/form/div[2]/div/label/input')
        write_username.send_keys(hyperparameters['username'])
        write_password = driver.find_element_by_xpath('/html/body/span/section/main/div/article/div/div[1]/div/form/div[3]/div/label/input')
        write_password.send_keys(hyperparameters['password'])
        write_password.send_keys(Keys.ENTER)
        time.sleep(2)
    except NoSuchElementException as exc:
        logging.info(exc)
        logging.info('Already logged in!\n')
    finally:
        if(driver.current_url != 'https://www.instagram.com/explore/'):
            raise FailedLoginError
        
        logging.info('Successfull login')
        logging.info(f'Redirecting to {hyperparameters["user_id"]}\'s page...\n')
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
    logging.info('Scrolling through followers\' scroll box:')
    for i in range(int(users_count / 11)): #it is divided by 11 because each iteration scrolls through 11 users
        time.sleep(random.randint(500,1000)/1000)
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", dialog)

    page_source = driver.page_source
    dom_BS=BeautifulSoup(page_source, "lxml") #BS stands for Beautiful Soup !!!

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
    logging.info('Getting users')
    driver = webdriver.Chrome("/Users/igor/Downloads/chromedriver")
    
    reloging = False
    failed_attemps = 0

    while failed_attemps < hyperparameters['login_retries']:
        try:
            login(driver, hyperparameters, reloging)
        except FailedLoginError:
            logging.info('Login failled!\n')
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
        logging.info('Tryging to get users count while not at user\'s page')
        logging.info(f'Redirecting to {hyperparameters["user_id"]}\'s page...\n')
        driver.get('https://www.instagram.com/' + hyperparameters['user_id'])
        time.sleep(2)
        users_count = getUsersCount(driver, type_)
        
        
    failed_attemps = 0

    while failed_attemps < hyperparameters['get_users_retries']:
        try:
            users_list = getUsersList(driver, users_count, type_)
        except Exception as exc:
            logging.info('Failed getting users!\n')
            logging.info(exc)
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


if __name__ == '__main__':
    main()
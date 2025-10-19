'''
Author:     Sai Vignesh Golla
LinkedIn:   https://www.linkedin.com/in/saivigneshgolla/

Copyright (C) 2024 Sai Vignesh Golla

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html
            
GitHub:     https://github.com/GodsScion/Auto_job_applier_linkedIn

version:    24.12.29.12.30
'''




# from config.XdepricatedX import *

import os

__validation_file_path = ""

def check_int(var: int, var_name: str, min_value: int=0) -> bool | TypeError | ValueError:
    if not isinstance(var, int): raise TypeError(f'The variable "{var_name}" in "{__validation_file_path}" must be an Integer!\nReceived "{var}" of type "{type(var)}" instead!\n\nSolution:\nPlease open "{__validation_file_path}" and update "{var_name}" to be an Integer.\nExample: `{var_name} = 10`\n\nNOTE: Do NOT surround Integer values in quotes ("10")X !\n\n')
    if var < min_value: raise ValueError(f'The variable "{var_name}" in "{__validation_file_path}" expects an Integer greater than or equal to `{min_value}`! Received `{var}` instead!\n\nSolution:\nPlease open "{__validation_file_path}" and update "{var_name}" accordingly.')
    return True

def check_boolean(var: bool, var_name: str) -> bool | ValueError:
    if var == True or var == False: return True
    raise ValueError(f'The variable "{var_name}" in "{__validation_file_path}" expects a Boolean input `True` or `False`, not "{var}" of type "{type(var)}" instead!\n\nSolution:\nPlease open "{__validation_file_path}" and update "{var_name}" to either `True` or `False` (case-sensitive, T and F must be CAPITAL/uppercase).\nExample: `{var_name} = True`\n\nNOTE: Do NOT surround Boolean values in quotes ("True")X !\n\n')

def check_string(var: str, var_name: str, options: list=[], min_length: int=0) -> bool | TypeError | ValueError:
    if not isinstance(var, str): raise TypeError(f'Invalid input for {var_name}. Expecting a String!')
    if min_length > 0 and len(var) < min_length: raise ValueError(f'Invalid input for {var_name}. Expecting a String of length at least {min_length}!')
    if len(options) > 0 and var not in options: raise ValueError(f'Invalid input for {var_name}. Expecting a value from {options}, not {var}!')
    return True

def check_list(var: list, var_name: str, options: list=[], min_length: int=0) -> bool | TypeError | ValueError:
    if not isinstance(var, list): 
        raise TypeError(f'Invalid input for {var_name}. Expecting a List!')
    if len(var) < min_length: raise ValueError(f'Invalid input for {var_name}. Expecting a List of length at least {min_length}!')
    for element in var:
        if not isinstance(element, str): raise TypeError(f'Invalid input for {var_name}. All elements in the list must be strings!')
        if len(options) > 0 and element not in options: raise ValueError(f'Invalid input for {var_name}. Expecting all elements to be values from {options}. This "{element}" is NOT in options!')
    return True



from config.personals import *
def validate_personals() -> None | ValueError | TypeError:
    '''
    Validates all variables in the `/config/personals.py` file.
    '''
    global __validation_file_path
    __validation_file_path = "config/personals.py"

    check_string(first_name, "first_name", min_length=1)
    check_string(middle_name, "middle_name")
    check_string(last_name, "last_name", min_length=1)

    check_string(phone_number, "phone_number", min_length=10)

    check_string(current_city, "current_city")
    
    check_string(street, "street")
    check_string(state, "state")
    check_string(zipcode, "zipcode")
    check_string(country, "country")
    
    check_string(ethnicity, "ethnicity", ["Decline", "Hispanic/Latino", "American Indian or Alaska Native", "Asian", "Black or African American", "Native Hawaiian or Other Pacific Islander", "White", "Other"],  min_length=0)
    check_string(gender, "gender", ["Male", "Female", "Other", "Decline", ""])
    check_string(disability_status, "disability_status", ["Yes", "No", "Decline"])
    check_string(veteran_status, "veteran_status", ["Yes", "No", "Decline"])



from config.questions import *
def validate_questions() -> None | ValueError | TypeError:
    '''
    Validates all variables in the `/config/questions.py` file.
    '''
    global __validation_file_path
    __validation_file_path = "config/questions.py"

    check_string(default_resume_path, "default_resume_path")
    check_string(years_of_experience, "years_of_experience")
    check_string(require_visa, "require_visa", ["Yes", "No"])
    check_string(website, "website")
    check_string(linkedIn, "linkedIn")
    check_int(desired_salary, "desired_salary")
    check_string(us_citizenship, "us_citizenship", ["U.S. Citizen/Permanent Resident", "Non-citizen allowed to work for any employer", "Non-citizen allowed to work for current employer", "Non-citizen seeking work authorization", "Canadian Citizen/Permanent Resident", "Other"])
    check_string(linkedin_headline, "linkedin_headline")
    check_int(notice_period, "notice_period")
    check_int(current_ctc, "current_ctc")
    check_string(linkedin_summary, "linkedin_summary")
    check_string(cover_letter, "cover_letter")
    check_string(recent_employer, "recent_employer")
    check_string(confidence_level, "confidence_level")

    check_boolean(pause_before_submit, "pause_before_submit")
    check_boolean(pause_at_failed_question, "pause_at_failed_question")
    check_boolean(overwrite_previous_answers, "overwrite_previous_answers")


import config.search as search_config
def validate_search() -> None | ValueError | TypeError:
    '''
    Validates all variables in the `/config/search.py` file.
    '''
    global __validation_file_path
    __validation_file_path = "config/search.py"

    def _require(attr: str, default, required: bool = False):
        if hasattr(search_config, attr):
            return getattr(search_config, attr)
        if required:
            raise ValueError(f'Missing required variable "{attr}" in config/search.py')
        return default

    search_terms = _require("search_terms", [], required=True)
    check_list(search_terms, "search_terms", min_length=1)

    search_location_value = _require("search_location", "")
    check_string(search_location_value, "search_location")

    switch_number = _require("switch_number", None, required=True)
    check_int(switch_number, "switch_number", 1)
    randomize_search_order = _require("randomize_search_order", False, required=True)
    check_boolean(randomize_search_order, "randomize_search_order")

    sort_by = _require("sort_by", "")
    check_string(sort_by, "sort_by", ["", "Most recent", "Most relevant"])
    date_posted = _require("date_posted", "")
    check_string(date_posted, "date_posted", ["", "Any time", "Past month", "Past week", "Past 24 hours"])
    salary = _require("salary", "")
    check_string(salary, "salary")

    easy_apply_only = _require("easy_apply_only", False, required=True)
    check_boolean(easy_apply_only, "easy_apply_only")

    experience_level = _require("experience_level", [])
    check_list(experience_level, "experience_level", ["Internship", "Entry level", "Associate", "Mid-Senior level", "Director", "Executive"])
    job_type = _require("job_type", [])
    check_list(job_type, "job_type", ["Full-time", "Part-time", "Contract", "Temporary", "Volunteer", "Internship", "Other"])
    on_site = _require("on_site", [])
    check_list(on_site, "on_site", ["On-site", "Remote", "Hybrid"])

    companies = _require("companies", [])
    check_list(companies, "companies")
    location = _require("location", [])
    check_list(location, "location")
    industry = _require("industry", [])
    check_list(industry, "industry")
    job_function = _require("job_function", [])
    check_list(job_function, "job_function")
    job_titles = _require("job_titles", [])
    check_list(job_titles, "job_titles")

    benefits = getattr(search_config, "benefits", None)
    if benefits is not None:
        check_list(benefits, "benefits")
    commitments = getattr(search_config, "commitments", None)
    if commitments is not None:
        check_list(commitments, "commitments")

    under_10_applicants = _require("under_10_applicants", False, required=True)
    check_boolean(under_10_applicants, "under_10_applicants")
    in_your_network = _require("in_your_network", False, required=True)
    check_boolean(in_your_network, "in_your_network")
    fair_chance_employer = _require("fair_chance_employer", False, required=True)
    check_boolean(fair_chance_employer, "fair_chance_employer")

    pause_after_filters = _require("pause_after_filters", False, required=True)
    check_boolean(pause_after_filters, "pause_after_filters")

    about_company_bad_words = _require("about_company_bad_words", [])
    check_list(about_company_bad_words, "about_company_bad_words")
    about_company_good_words = _require("about_company_good_words", [])
    check_list(about_company_good_words, "about_company_good_words")
    bad_words = _require("bad_words", [])
    check_list(bad_words, "bad_words")

    security_clearance = _require("security_clearance", False, required=True)
    check_boolean(security_clearance, "security_clearance")
    did_masters = _require("did_masters", False, required=True)
    check_boolean(did_masters, "did_masters")
    current_experience = _require("current_experience", 0, required=True)
    check_int(current_experience, "current_experience", -1)

def validate_environment() -> None | ValueError:
    required = ["LINKEDIN_EMAIL", "LINKEDIN_PASSWORD"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

from config.settings import *
def validate_settings() -> None | ValueError | TypeError:
    '''
    Validates all variables in the `/config/settings.py` file.
    '''
    global __validation_file_path
    __validation_file_path = "config/settings.py"

    check_boolean(close_tabs, "close_tabs")
    check_boolean(follow_companies, "follow_companies")
    # check_boolean(connect_hr, "connect_hr")
    # check_string(connect_request_message, "connect_request_message", min_length=10)

    check_boolean(run_non_stop, "run_non_stop")
    check_boolean(alternate_sortby, "alternate_sortby")
    check_boolean(cycle_date_posted, "cycle_date_posted")
    check_boolean(stop_date_cycle_at_24hr, "stop_date_cycle_at_24hr")
    
    # check_string(generated_resume_path, "generated_resume_path", min_length=1)

    check_string(file_name, "file_name", min_length=1)
    check_string(failed_file_name, "failed_file_name", min_length=1)
    check_string(logs_folder_path, "logs_folder_path", min_length=1)

    check_int(click_gap, "click_gap", 0)

    check_boolean(run_in_background, "run_in_background")
    check_boolean(disable_extensions, "disable_extensions")
    check_boolean(safe_mode, "safe_mode")
    check_boolean(smooth_scroll, "smooth_scroll")
    check_boolean(keep_screen_awake, "keep_screen_awake")
    check_boolean(stealth_mode, "stealth_mode")




def validate_config() -> bool | ValueError | TypeError:
    '''
    Runs all validation functions to validate all variables in the config files.
    '''
    validate_environment()
    validate_personals()
    validate_questions()
    validate_search()
    validate_settings()

    # validate_String(chatGPT_username, "chatGPT_username")
    # validate_String(chatGPT_password, "chatGPT_password")
    # validate_String(chatGPT_resume_chat_title, "chatGPT_resume_chat_title")
    return True

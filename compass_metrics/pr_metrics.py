""" Set of pr related metrics """

from compass_metrics.db_dsl import (get_uuid_count_query,
                                    get_pr_closed_uuid_count,
                                    get_pr_message_count,
                                    get_pr_linked_issue_count)
from datetime import timedelta
from compass_common.datetime import get_time_diff_days
from compass_common.datetime import str_to_datetime
from compass_common.algorithm_utils import get_medium


def pr_open_time(client, pr_index, date, repos_list):
    query_pr_opens = get_uuid_count_query(
        "avg", repos_list, "time_to_first_attention_without_bot", "grimoire_creation_date", size=10000,
        from_date=date-timedelta(days=90), to_date=date)
    query_pr_opens["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true"}})
    pr_opens_items = client.search(index=pr_index, body=query_pr_opens)['hits']['hits']
    if len(pr_opens_items) == 0:
        return { "pr_open_time_avg": None, "pr_open_time_mid": None }
    pr_open_time_repo = []
    for item in pr_opens_items:
        if 'state' in item['_source']:
            if item['_source']['state'] == 'merged' and item['_source']['merged_at'] and str_to_datetime(item['_source']['merged_at']) < date:
                pr_open_time_repo.append(get_time_diff_days(
                    item['_source']['created_at'], item['_source']['merged_at']))
            if item['_source']['state'] == 'closed' and str_to_datetime(item['_source']['closed_at'] or item['_source']['updated_at']) < date:
                pr_open_time_repo.append(get_time_diff_days(
                    item['_source']['created_at'], item['_source']['closed_at'] or item['_source']['updated_at']))
            else:
                pr_open_time_repo.append(get_time_diff_days(item['_source']['created_at'], str(date)))

    pr_open_time_repo_avg = float(sum(pr_open_time_repo)/len(pr_open_time_repo)) if len(pr_open_time_repo) > 0 else None
    pr_open_time_repo_mid = get_medium(pr_open_time_repo) if len(pr_open_time_repo) > 0 else None

    result = {
        "pr_open_time_avg": pr_open_time_repo_avg,
        "pr_open_time_mid": pr_open_time_repo_mid
    }
    return result


def code_review_count(client, pr_index, date, repo_list):
    query_pr_comments_count = get_uuid_count_query(
            "avg", repo_list, "num_review_comments_without_bot", size=0, from_date=(date-timedelta(days=90)), to_date=date)
    query_pr_comments_count["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true" }})
    prs = client.search(index=pr_index, body=query_pr_comments_count)
    if prs["hits"]["total"]["value"] == 0:
        comment_count = None
    else:
        comment_count = prs['aggregations']["count_of_uuid"]['value']
    result = {
        'code_review_count': round(comment_count, 4) if comment_count is not None else None
    }
    return result


def close_pr_count(client, pr_index, date, repos_list):
    """ The number of PR accepted and declined in the last 90 days. """
    query_pr_closed = get_pr_closed_uuid_count(
        "cardinality", repos_list, "uuid", from_date=(date-timedelta(days=90)), to_date=date)
    pr_closed = client.search(index=pr_index, body=query_pr_closed)[
        'aggregations']["count_of_uuid"]['value']

    result = {
        "close_pr_count": pr_closed
    }
    return result


def pr_time_to_first_response(client, pr_index, date, repos_list):
    """ Determine the amount of time between when a PR was created and when it received the first response from a human
    in the past 90 days. """
    query_pr_first_response_avg = get_uuid_count_query(
        "avg", repos_list, "time_to_first_attention_without_bot", "grimoire_creation_date", size=0,
        from_date=date - timedelta(days=90), to_date=date)
    query_pr_first_response_avg["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true"}})
    pr_first_response = client.search(index=pr_index, body=query_pr_first_response_avg)
    pr_first_response_avg = pr_first_response['aggregations']["count_of_uuid"]['value']

    query_pr_first_response_mid = get_uuid_count_query(
        "percentiles", repos_list, "time_to_first_attention_without_bot", "grimoire_creation_date", size=0,
        from_date=date - timedelta(days=90), to_date=date)
    query_pr_first_response_mid["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true"}})
    query_pr_first_response_mid["aggs"]["count_of_uuid"]["percentiles"]["percents"] = [
        50]
    pr_first_response_mid = client.search(index=pr_index, body=query_pr_first_response_mid)[
        'aggregations']["count_of_uuid"]['values']['50.0']

    result = {
        'pr_time_to_first_response_avg': round(pr_first_response_avg, 4) if pr_first_response_avg is not None else None,
        'pr_time_to_first_response_mid': round(pr_first_response_mid, 4) if pr_first_response_mid is not None else None,
    }
    return result


def change_request_closure_ratio(client, pr_index, date, repos_list):
    """Measures the ratio between the total number of open change requests and the total number
    of closed change requests from the beginning to now."""
    close_pr_count = total_create_close_pr_count(client, pr_index, date, repos_list)["total_create_close_pr_count"]
    pr_count = total_pr_count(client, pr_index, date, repos_list)["total_pr_count"]

    result = {
        "change_request_closure_ratio": close_pr_count/pr_count if pr_count > 0 else None
    }
    return result


def change_request_closure_ratio_recently_period(client, pr_index, date, repos_list):
    """Measures the ratio between the total number of open change requests and the total number
    of closed change requests in the last 90 days."""
    close_pr_count = create_close_pr_count(client, pr_index, date, repos_list)["create_close_pr_count"]
    code_pr_count = pr_count(client, pr_index, date, repos_list)["pr_count"]

    result = {
        "change_request_closure_ratio_recently_period": close_pr_count/code_pr_count if code_pr_count > 0 else None
    }
    return result


def code_review_ratio(client, pr_index, date, repos_list):
    """ Determine the percentage of code commits with at least one reviewer (not PR creator) in the last 90 days. """
    code_pr_count = pr_count(client, pr_index, date, repos_list)["pr_count"]
    review_count = pr_count_with_review(client, pr_index, date, repos_list)["pr_count_with_review"]
    result = {
        "code_review_ratio": review_count/code_pr_count if code_pr_count > 0 else None
    }
    return result


def pr_count(client, pr_index, date, repos_list):
    """ The number of PR created from the beginning to now """
    query_pr_count = get_uuid_count_query(
        "cardinality", repos_list, "uuid", size=0, from_date=(date-timedelta(days=90)), to_date=date)
    query_pr_count["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true"}})
    query_pr_count["aggs"]["count_of_uuid"]["cardinality"]["precision_threshold"] = 100000
    pr_count = client.search(index=pr_index, body=query_pr_count)['aggregations']["count_of_uuid"]['value']
    result = {
        "pr_count": pr_count
    }
    return result


def pr_count_with_review(client, pr_index, date, repos_list):
    """ The Number of pr with review in the last 90 days """
    query_pr_body = get_pr_message_count(repos_list, "uuid", "grimoire_creation_date", size=0,
                                         filter_field="num_review_comments_without_bot", from_date=(date-timedelta(days=90)), to_date=date)
    prs = client.search(index=pr_index, body=query_pr_body)[
        'aggregations']["count_of_uuid"]['value']
    result = {
        "pr_count_with_review": prs
    }
    return result 


def code_merge_ratio(client, pr_index, date, repos_list):
    """ Determine the percentage of PR Mergers and PR authors who are not the same person in the last 90 days of commits. """
    merge_count_with_non_author = code_merge_count_with_non_author(client, pr_index, date, repos_list)["code_merge_count_with_non_author"]
    merge_count = code_merge_count(client, pr_index, date, repos_list)["code_merge_count"]
    
    result = {
        "code_merge_ratio": merge_count_with_non_author/merge_count if merge_count > 0 else None
    }
    return result


def pr_issue_linked_ratio(client, pr_index, pr_comments_index, date, repos_list):
    """ Determine the percentage of new pull request link issues in the last 90 days. """
    code_pr_count = pr_count(client, pr_index, date, repos_list)["pr_count"]
    code_pr_issue_linked_count = pr_issue_linked_count(client, pr_index, pr_comments_index, date, repos_list)["pr_issue_linked_count"]
    result = {
        "pr_issue_linked_ratio": code_pr_issue_linked_count/code_pr_count if code_pr_count > 0 else None
    }
    return result


def total_create_close_pr_count(client, pr_index, date, repos_list):
    """The number of pr created from the beginning to now and it has been accepted and declined"""
    from_date = str_to_datetime("1970-01-01")
    pr_total_dsl = get_uuid_count_query(
        "cardinality", repos_list, "uuid", size=0, from_date=from_date, to_date=date)
    pr_total_dsl["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true"}})
    pr_total_dsl["aggs"]["count_of_uuid"]["cardinality"]["precision_threshold"] = 100000

    pr_closed_dsl = pr_total_dsl
    pr_closed_dsl["query"]["bool"]["must"][0]["bool"]["filter"].append({
                                    "range": {
                                        "closed_at": {
                                            "gte": from_date.strftime("%Y-%m-%d"),
                                            "lt": date.strftime("%Y-%m-%d")
                                        }
                                    }
                                })
    pr_closed_count = client.search(index=pr_index, body=pr_closed_dsl)['aggregations']["count_of_uuid"]['value']
    result = {
        "total_create_close_pr_count": pr_closed_count
    }
    return result


def total_pr_count(client, pr_index, date, repos_list):
    """ The number of PR created in the last 90 days. """
    query_pr_count = get_uuid_count_query(
        "cardinality", repos_list, "uuid", size=0, from_date=str_to_datetime("1970-01-01"), to_date=date)
    query_pr_count["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true"}})
    query_pr_count["aggs"]["count_of_uuid"]["cardinality"]["precision_threshold"] = 100000
    pr_count = client.search(index=pr_index, body=query_pr_count)['aggregations']["count_of_uuid"]['value']
    result = {
        "total_pr_count": pr_count
    }
    return result


def create_close_pr_count(client, pr_index, date, repos_list):
    """The number of pr created in the last 90 days and it has been accepted and declined"""
    from_date = date - timedelta(days=90)
    pr_total_dsl = get_uuid_count_query(
        "cardinality", repos_list, "uuid", size=0, from_date=from_date, to_date=date)
    pr_total_dsl["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true"}})
    pr_total_dsl["aggs"]["count_of_uuid"]["cardinality"]["precision_threshold"] = 100000

    pr_closed_dsl = pr_total_dsl
    pr_closed_dsl["query"]["bool"]["must"][0]["bool"]["filter"].append({
                                    "range": {
                                        "closed_at": {
                                            "gte": from_date.strftime("%Y-%m-%d"),
                                            "lt": date.strftime("%Y-%m-%d")
                                        }
                                    }
                                })
    pr_closed_count = client.search(index=pr_index, body=pr_closed_dsl)['aggregations']["count_of_uuid"]['value']
    result = {
        "create_close_pr_count": pr_closed_count
    }
    return result


def code_merge_count_with_non_author(client, pr_index, date, repos_list):
    """ Determine the Numbers of PR Mergers and PR authors who are not the same person in the last 90 days of commits. """
    query_pr_body = get_uuid_count_query("cardinality", repos_list, "uuid", "grimoire_creation_date", size=0, from_date=(date-timedelta(days=90)), to_date=date)
    query_pr_body["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true"}})
    query_pr_body["query"]["bool"]["must"].append({"match_phrase": {"merged": "true"}})
    query_pr_body["query"]["bool"]["must"].append({
                        "script": {
                            "script": "if(doc['merged_by_data_name'].size() > 0 && doc['author_name'].size() > 0 && doc['merged_by_data_name'].value !=  doc['author_name'].value){return true}"
                        }
                    })
    prs = client.search(index=pr_index, body=query_pr_body)[
        'aggregations']["count_of_uuid"]['value']
    
    result = {
        "code_merge_count_with_non_author": prs
    }
    return result


def code_merge_count(client, pr_index, date, repos_list):
    """ Determine the Numbers of PR merge in the last 90 days of commits. """
    query_pr_body = get_uuid_count_query("cardinality", repos_list, "uuid", "grimoire_creation_date", size=0, from_date=(date-timedelta(days=90)), to_date=date)
    query_pr_body["query"]["bool"]["must"].append({"match_phrase": {"pull_request": "true"}})
    query_pr_body["query"]["bool"]["must"].append({"match_phrase": {"merged": "true"}})
    pr_merged_count = client.search(index=pr_index, body=query_pr_body)[
        'aggregations']["count_of_uuid"]['value']
    result = {
        "code_merge_count": pr_merged_count
    }
    return result


def pr_issue_linked_count(client, pr_index, pr_comments_index, date, repos_list):
    """ Determine the Numbers of new pull request link issues in the last 90 days. """
    pr_linked_issue = 0
    for repo in repos_list:
        query_pr_linked_issue = get_pr_linked_issue_count(
            repo, from_date=date-timedelta(days=90), to_date=date)
        pr_linked_issue += client.search(index=(pr_index, pr_comments_index), body=query_pr_linked_issue)[
            'aggregations']["count_of_uuid"]['value']
    result = {
        "pr_issue_linked_count": pr_linked_issue,
    }
    return result
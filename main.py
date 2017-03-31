from bsddb3 import db

from phase1 import get_text

class Node:

    def __init__(self, data=None, next_node=None):
        """Node object for linked list

        :param data: dictionary containing term, prefix, and code
        :param next_node: what current node is pointing to
        """
        self.data = data
        self.next_node = next_node

    def get_data(self):
        return self.data

    def get_next(self):
        return self.next_node

    def set_next(self, node):
        self.next_node = node


class LinkedList:

    def __init__(self, head=None):
        """Singly linked list consisting of nodes
        Each node contains a one-word query term
        """
        self.head = head

    def insert(self, data):
        """Inserts a new node into the linked list based on data values

        Each data dictionary contains a code that corresponds to a 
        query term. Ensures that nodes are stored in ascending order of
        code values.
        :param data: dictionary with query term code
        """
        code = data['code']
        current = self.head
        previous = None

        while current != None:
            cur_data = current.get_data()
            other_code = cur_data['code']

            # Insert new node before node with higher code value
            if code <= other_code:
                break
            else: 
                previous = current
                current = current.get_next() 
         
        new_node = Node(data, current)
        if previous is None:
            self.head = new_node            
        else:
            previous.set_next(new_node)

    def get_head(self):
        """Get the first node in the linked list"""
        return self.head 


class Query:
    """
    alphanumeric    ::= [0-9a-zA-Z_]
    date            ::= year '/' month '/' day
    datePrefix      ::= 'date' (':' | '>' | '<')
    dateQuery       ::= dataPrefix date
    termPrefix      ::= ('text' | 'name' | 'location') ':'
    term            ::= alphanumeric
    termPattern     ::= alphanumeric '%'
    termQuery       ::= termPrefix? (term | termPattern)
    expression      ::= termQuery | dateQuery
    query           ::= expression | (expression whitespace)+
    """
    
    def __init__(self, dates_db, terms_db, query):
        """
        Class for parsing queries and returning matches from the Berkeley
        database.

        :param dates_db: dates database with date as key
        :param terms_db: terms database with term as key
        :param query: query string from user input
        """
        self.dates_db = dates_db
        self.terms_db = terms_db 
        self.t_prefixes = ['text:', 'name:', 'location:']
        self.d_prefixes = ['date:', 'date<', 'date>']

        self.terms = query.split()
        self.linked_list = LinkedList()
        self.results = None 
        self.sort_terms()

    #---------------------------------------------------------------------------

    def get_results(self):
        """Get the results of the query. After the order of the terms are sorted
        into a linked list, get the results of each term and intersect them with
        the current result matches.
        """
        current = self.linked_list.get_head()
        while current != None:
            data = current.get_data()
            query = data['term']
            prefix = data['prefix']

            if prefix is None or 'date' not in prefix:
                records = self.get_terms(query, prefix)
            else:
                records = self.get_dates(query, prefix[-1])

            if len(records) == 0:
                # If a query term returns nothing, immediately exitt
                self.results = set()
                break
            elif self.results is None:
                self.results = records
            else:
                self.results = self.results.intersection(records)

            # Immediately exit if intersecting produces nothing
            if self.results and len(self.results) == 0:
                break 
            current = current.get_next()

        if self.results:
            return sorted(self.results)
        else:
            return [] 

    #---------------------------------------------------------------------------

    def sort_terms(self):
        """Sort individual query terms. Terms with prefixes/exact queries are
        considered first because they are more likely to return smaller result
        sets than partial/range queries.

        Term order is maintained by storing each term in a linked list.
        """
        for term in self.terms:
            prefix = None
            mid = None
            word = term

            if len(term) > 0 and term[-1] == '%':
                partial = True
            else:
                partial = False

            if ':' in term:
                mid = ':'
            elif '>' in term:
                mid = '>'
            elif '<' in term:
                mid = '<'
            
            if mid:
                prefix, word = term.split(mid)
            code = self.classify_term(word, prefix, mid, partial)

            if prefix:
                if not self.valid_prefixes(prefix + mid): 
                    prefix = None
                    word = term
                else:
                    prefix += mid

            # Data to be stored in node
            data = {'code': code, 'prefix': prefix, 'term': word}
            self.linked_list.insert(data)
 
    #---------------------------------------------------------------------------

    def valid_prefixes(self, prefix):
        """Returns True if the prefix is a valid prefix"""
        if prefix in self.t_prefixes or prefix in self.d_prefixes:
            return True
        else:
            return False

    #---------------------------------------------------------------------------

    def classify_term(self, term, prefix, mid, partial):
        """Determine the code value for a term. The lower the return value, the
        earlier the term query should be processed.

        :param term: single keyword
        :param prefix: either name, location, text, or date
        :param mid: either None, :, <, or >
        :param partial: True if mid is < or >
        """
        if prefix == 'date':
            if mid == ':':
                return 4
            else:
                return 9
        elif partial:
            if prefix == 'name':
                return 6
            elif prefix == 'location':
                return 7
            elif prefix == 'text':
                return 8
            else:
                return 10
        else:
            if prefix == 'name':
                return 1
            elif prefix == 'location':
                return 2
            elif prefix == 'text':
                return 3
            else:
                return 5 
        
    #---------------------------------------------------------------------------

    def get_terms(self, term, prefix):
        """Match tweet records to term queries with the prefix location:, name:,
        or text: or to all of them if term query has no prefix
        """
        if len(term) > 0 and term[-1] == '%':
            partial = True
            term = term[:-1]
        else:
            partial = False 
                    
        if prefix is None:
            # If term query has no term prefix
            return self.match_general(term, partial)
        else:
            # If term query has a prefix
            query = (prefix[0] + '-' + term)
            return self.match_query(self.terms_db, query, partial)

    #---------------------------------------------------------------------------

    def match_general(self, term, partial=False):
        """Check if term matches any records with the prefix location:, name:,
        and text:

        :param term: keyword with no prefix
        :param partial: True if partial, False if exact
        """ 
        matches = set()
        prefixes = ['l-', 'n-', 't-']

        for i in range(3):
            curs = self.terms_db.cursor()
            query_str = prefixes[i] + term
            key = query_str.encode('utf-8')

            if partial:
                iter = curs.set_range(key)
            else:
                iter = curs.set(key)

            while iter and term in iter[0].decode('utf-8'):
                result = curs.get(db.DB_CURRENT)
                matches.add(result[1])
  
                if partial:
                    iter = curs.next()
                else:
                    iter = curs.next_dup()
            curs.close()

        return matches

    #---------------------------------------------------------------------------
        
    def match_query(self, q_db, query, partial=False):
        """Match keywords with an exact match or terms with a colon in the prefix
        Used for both term and date queries

        :param q_db: dates or term database
        :param query: potential key found in database
        :param partial: True if partial, False if exact
        """ 
        matches = set()
        curs = q_db.cursor()
        key = query.encode('utf-8')

        if partial:
            iter = curs.set_range(key)
        else:
            iter = curs.set(key)

        while iter and query in iter[0].decode('utf-8'):
            result = curs.get(db.DB_CURRENT)
            matches.add(result[1])
 
            if partial:
                iter = curs.next()
            else:
                iter = curs.next_dup()

        curs.close()
        return matches

    #---------------------------------------------------------------------------

    def get_dates(self, date, mid):
        """Matches tweet records to date query. Date query can be an exact or
        range query
        """
        if mid == ':': 
            return self.match_query(self.dates_db, date)
        else:
            return self.match_range(date, mid)

    #---------------------------------------------------------------------------

    def match_range(self, date, mid):
        """Match range date queries to find records either below/above the date

        :param date: date query
        :param mid: either < or >
        """
        curs1 = self.dates_db.cursor()
        matches = set()

        date = date.encode('utf-8')
        curs1.set_range(date)

        # Determine which index to start iterating at
        if mid == '<':
            iter = curs1.first()
        else: 
            iter = curs1.next_nodup()

        # Iterate until the query date or the end of database
        while iter: 
            if mid == '<' and iter[0] >= date:
                break 
            matches.add(iter[1])
            iter = curs1.next()

        curs1.close()
        return matches 

    #---------------------------------------------------------------------------


def display_record(tw_db, tw_id):
    curs = tw_db.cursor()
    record = curs.set(tw_id)[1].decode('utf-8')
    curs.close()

    date = get_text(record, 'created_at')
    text = get_text(record, 'text')
    rt_count = get_text(record, 'retweet_count')
    name = get_text(record, 'name')
    location = get_text(record, 'location')
    description = get_text(record, 'description')
    url = get_text(record, 'url')

    print("Record ID: " + tw_id.decode('utf-8'))    
    print("Created at: %s\nText: %s\nRetweet count: %s" % (date, text, rt_count))
    print("Name: %s\nLocation: %s" % (name, location))
    print("Description: %s\nUrl: %s" % (description, url)) 


#-------------------------------------------------------------------------------


def main():
    # Dates database with date as key, tweet record as value
    database1 = db.DB()
    database1.open('da.idx')

    # Terms database with term query as key, tweet record as value
    database2 = db.DB()
    database2.open('te.idx')

    # Tweets database with tweet record as key, tweet info as value
    database3 = db.DB()
    database3.open('tw.idx')

    # Get user query input
    again = 'y'
    affirmatives = ['y', 'yes', '1'] 
    while again in affirmatives: 
        query = input("Enter query: ").lower()

        # Parse the query and return tweet records that match query
        q = Query(database1, database2, query)
        results = q.get_results()
    
        # Output the results
        border = '-' * 100 
        for result in results:
            print(border)
            display_record(database3, result)
    
        if len(results) > 0:
            print(border)
        if len(results) == 1:
            print("1 record found.")
        else:
            print("%d records found." % (len(results))) 

        again = input("Do you want to make another query? y/n: ").lower()

    database1.close()
    database2.close()
    database3.close()

if __name__ == "__main__":
    main()

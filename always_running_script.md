# Always Running Script
## The Flows I want to enable
### Always Running Script
- This will be a python script that runs a similar process to the current on demand script with a few exceptions
- It will run locally on my computer as a background process. Ideally it will also be able to restart itself if I restart my computer
- every 3 hours it will
    - check if there is an internet connection and if not quit
    - query notion and all notes in the database by date created that has the Kindling Research check box set to true and run the research loop if they are missing the Kindling Research block
    - save the ids of pages that you researched to a file so that we can pull these pages later
    - continue to loop until all pages have been researched
- If any errors or exceptions occur these should be caught and logged as well
- If the time is past 6pm in the timezone of the computer create a simple email that lists out all the pages that have been researched that you have logged and send it to sarkalgud@gmail.com
    - For each page include a link to the page as well as the everything up untl TLDR for the page
    - include the total cost of research
    - Include any errors that were thrown (try to give a human readable error diagnoses if possible)
- Clear the queue of ids you stored in the file
### Script To Track The Background Script**
- This is a python script I can run in my terminal to track this background process to see if it’s running ,read any errors or issues that are happening. Basically a dashboard for the background process
- I should also have the ability to stop the background process, restart it, run it etc.
- I should also have the ability to change the interval at which it is run and also when the email is sent out
- Use a simple TUI
## Implementation Details
- Please provide any instructions in terms of giving the script permissions etc. to the Read Me and also in your output after you've finished coding.
## Technical Details
- I've included environment variables GMAIL_USER, GMAIL_APP_PASSWORD that point to a gmail accoun you can send emails from
- here are the details from the SMPT EMail server for gmail
```
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
```
- I would suggest doing a light refactor of the code that is already written to split different parts of the functionality into separate files for better readabilitiy. I would like to keep an ability to run this on deman script.
## Validation
- Write unit tests and integration tests to validate that as much of this logic works as possible and when you are done developing explain what tests you have written
- Most of the validation will come from me running the thing
# Prompt Task 2 Notes

## **Claude**
### **Frotiers in Psychology**
*No answer, max 5 references, full APA citations.*
*$1.38*
* Questions 1-5
  * $0.05
* Questions 6-10
  * Input tokens: 1,141 | Output tokens: 2,694 | Stop reason: end_turn 
  * $0.08 total
  * $0.016 for each question
* Questions 11-20
  * Input tokens: 1,869 | Output tokens: 5,217 | Stop reason: end_turn
  * $0.14 total
  * $0.014 for each question
* Questions 21-40
  * Input tokens: 3,187 | Output tokens: 9,898 | Stop reason: end_turn
  * $0.26 total
  * $0.013 for each question
* Questions 41-100
  * 41-60
    * Input tokens: 2,989 | Output tokens: 9,932 | Stop reason: end_turn
  * 61-80
    * Input tokens: 3,137 | Output tokens: 11,000 | Stop reason: end_turn
  * 81-100
    * Input tokens: 2,852 | Output tokens: 11,254 | Stop reason: end_turn
  * $0.85 total
  * $0.014 for each question

## **Expert Systems with Applications**
*No answer, max 5 references, only first author, title, DOI.*
*$0.84*
* Questions 1-5
  * Input tokens: 1,272 | Output tokens: 1,403 | Stop reason: end_turn
  * $0.04 total
  * $0.008 for each question
* Questions 6-20
  * Input tokens: 2,698 | Output tokens: 4,057 | Stop reason: end_turn
  * $0.12 total
  * $0.008 for each question
* Questions 21-100
  * 21-40
    * Input tokens: 3,431 | Output tokens: 6,025 | Stop reason: end_turn
  * 41-60
    * Input tokens: 3,050 | Output tokens: 6,330 | Stop reason: end_turn
  * 61-80
    * Input tokens: 3,022 | Output tokens: 5,290 | Stop reason: end_turn
  * 81-100 — THIS FAILED FOR SOME REASON??? Returned empty array []
    * Input tokens: 3,118 | Output tokens: 488 | Stop reason: end_turn
  * $0.51 total
* Questions 81-100 (reran in batches of 10)
  * 81-90
    * Input tokens: 1,785 | Output tokens: 3,241 | Stop reason: end_turn
  * 91-100
    * Input tokens: 1,805 | Output tokens: 2,948 | Stop reason: end_turn
  * $0.17 total

## **American Economic, Physical Review, Lancet**

*No answer, max 5 references, only first author, title, DOI. Batch size 20. Ran simultaneously.*

*$2.39*


## **Total Environmental, Cell, Hazardous, IEE Neural Networks**

*No answer, max 5 references, only first author, title, DOI. Batch size 20. Ran simultaneously.*

*Claude "refused" to answer for Cell 81-100 in batches of 20 and 10?*

*Ran batches of 1 for Q81-90, worked fine. Refused again for 91?*

*$2.07* initial run

*$0.05* Q81-90, batch size 1

*$0.07* Q92-100, batch size 9

**Claude keeps refusing to answer Cell's Question 91??????**
"question": "How do the mutational constraints and antibody escape pathways mapped for the Nipah virus receptor-binding protein compare with those of other emerging henipaviruses, and how can these combined insights guide the development of broadly neutralizing, escape-resistant vaccines and therapies?"

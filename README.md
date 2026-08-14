# Investigating LLM and domain Bias in Hallucinated Author Citations  
This repository holds our data and code for our 2026 altREU project.  


## Overview  

[**Access our project overview here.**](docs/slides.md)  

This project investigates whether LLM-generated hallucinated citations are biased towards crediting highly cited, highly productive, or male authors.  

**Models**: GPT-5.5, Claude Opus 4.8, Gemini Flash 3.5  
**Domains**: Social sciences (subdomains: psychology and economics), computer science, medicine, physics, and environmental science  


## Background and Significance
LLMs are increasingly being used in academia to produce inaccurate work, with hallucinated citations being one quantifiable way of observing this. Citation-checking tools attempt to combat this by comparing references against databases like OpenAlex and Semantic Scholar to identify fake sources. Prior research has worked with these tools to study hallucinated citation prevalence and biases within published scientific literature. For example, Topaz et al. (2026) showed that hallucinated citations have been on the rise within biomedical research. On a broader scale, Zhao et al. (2026) examined 111 million references across 2.5 million papers on arXiv, bioRxiv, SSRN, and PubMed Central and found that hallucinated citations disproportionately cite prominent and male scholars, varying by academic discipline (*social sciences, CS, medicine, physics, environmental science* had the highest percentage of papers with hallucinated citations).  

However, studies like this only observe these patterns *after publication*, when human editing and review may have already altered the original bias expressed by an LLM. Thus, there is a lack of literature examining biases within LLMs in the specific domain of scientific authorship and citation production.  

Our project approaches this gap in the literature by generating citations directly from multiple LLMs under controlled prompting conditions. We prompt GPT-5.5, Claude-Opus-4.8, and Gemini-Flash-3.5 with identical literature-review tasks across several disciplines, identify hallucinated citations, and compare the characteristics (gender and productivity) of first authors referenced in those hallucinations. We compare rates across disciplines to support more in depth analysis for bias rates, controlling for gender rate differences within academic disciplines.  

Because prior work has already demonstrated clear citation biases within published papers that use AI, we expect that a sufficiently large sample of generated citations will allow us to detect significant differences between models. However, we believe that our approach using controlled prompting conditions, rather than examining published literature, will allow us to more accurately examine LLM bias as it looks at its raw output, rather than work that has potentially gone through review and/or editing by humans.  


## Research Question
Across three widely used LLMs (GPT-5.5, Claude Opus 4.8, and Gemini Flash 3.5) and five academic disciplines (social sciences, CS, medicine, physics, environmental science), do hallucinated author attributions in ~15,000 citations generated from identical literature-review prompts differ in how often they credit highly cited, highly productive, or male authors?


## Objectives
- Understand the relationship between LLM performance across different domains in generating verified and hallucinated citations.
- Compare different LLM performance in citation generation.
- Investigate author bias rates in LLM-generated hallucinated citations within the five domains and how they compare to known hallucinated author bias rates in published literature.


## Dataset  
**Domain Representation**: We chose two journals with high h5-indices from each domain. Since social sciences comprises of many distinct subdomains, we evaluated the chosen subdomains individually.  

**Social sciences**: *Frontiers in Psychology* and *American Economic Review* (analyzed as psychology and economics).  

**Computer science**: *Expert Systems with Applications* and *IEEE Transactions on Neural Networks and Learning Systems*  

**Medicine**: *Cell* and *The Lancet*  

**Physics**: *The Astrophysical Journal* and *Physical Review Letters*  

**Environmental science**: *The Science of The Total Environment* and *Journal of Hazardous Materials*  

## Methodology  
This is a brief overview of our methodology pipelines.  

**From paper abstract to LLM-generated citation:**  
Abstract collection —> Generate literature review-style questions —> Generate citations to support an answer to a question

**From LLM-generated citation to relevant data points (citation status, first author gender, first author productivity):**  
Citation verification —> First author verification —> First author analysis of gender and h-index  

For more detail, see our full methodology [here](docs/methodology.md).


## Results  
See visuals of our results:  
- [Hallucination rates](docs/figures/hallucination/hallu-figs.md)  
- [Author gender](docs/figures/gender/gender-figs.md)  
- [Author productivity](docs/figures/productivity/prod-figs.md)  

See how we calculated our results [here](docs/result_calcs.md).


**Some key results:**  
- Statistically significant **association between LLM and citation status** (hallucinated vs verified).  
  - ~48% citations were hallucinated overall.  
- Hallucination rates by LLM:  
  - GPT: 23.14%  
  - Claude: 30.18%  
  - Gemini: 82.14%  
- Statistically significant **association between domain and citation status**.  
  - Environmental science saw the highest hallucination rate of 73.30%. Economics saw the lowest hallucination rate of 27.33%  
  - In published works, social sciences have the highest hallucination rate and environmental sciences have the lowest out of the five domains evaluated.
- The **average h-index** of authors in **hallucinated citations** was **significantly higher** than the score of the **baseline**. 
  - Authors in hallucinated citations had an average h-index of 60, compared to our baseline of 14.  
- The **rate of male authors** in **hallucinated citations** is **comparable to rates in published works** (Zhao et al. (2026)).  
  - Higher number of male authors were seen in hallucinated citations. There was no significant difference in gender rates across LLMs.  


## Brief Discussion
We note that Gemini-Flash-3.5 likely has reduced reasoning skills compared to Gemini Pro models. One possible explanation for Gemini's higher high hallucination rate may be due to differences in model architecture, training, or reasoning abilities. However, our project does not directly investigate these factors.    

The higher hallucination rate observed in environmental science could be attributed to less relevant model training data and lower LLM usage within the domain. Again, this study does not directly investigate these factors. The reason for higher hallucination rates in environmental science has potential for future investigation.  

Although the observed gender and h-index biases were more pronounced compared ther baselines, the biases seem to reflect broader scientific trends.  


## Conclusion  
The LLMs show heightened biases in their generated citations, both real and hallucinated, with patterns relying on domain and model.  

These biases appear to differ from trends in published literature.  

The demographic biases (gender and h-index) are consistent with real-world trends.  


## Impact  
We hope that our project brings clarity for users and researchers to better understand LLM strengths and weaknesses in different domains.  

We also provide our full database for further analysis, as well as an extendable pipeline to analyze citations.


## Limitations  
We consider several limitations to our project.  
- LLM hallucination rate results may not be generalizable to other model versions.  
- Author gender determinations are predictions based on first names; they may not accurately represent all authors' genders.
- H-index may not accurately reflect the productivity of authors who are still early in their careers. H-index may also vary among databases.  


## Repository Structure  
```text
jhmz-altREU/
├── baseline-stats/       # Baseline values generation 
│
├── data/
│   ├── abstracts/        # Abstracts pulled from OpenAlex (500 per domain)
│   ├── final-raw-data/   # CSV files of relevant datapoints
│   ├── questions/        # Questions generated by all LLMs (1 per abstract)
│   ├── responses/
│   │   ├── anthropic/      # Citations generated by Claude (5 per question)
│   │   ├── gemini/         # Citations generated by Gemini (5 per question)
│   │   └── gpt/            # Citations generated by GPT (5 per question)
│   └── verification/     # Cleaned/processed data
│       ├── anthr/          # Verified citations (includes citation status, author gender, h-index)
│       ├── gemini/         # Verified citations (includes citation status, author gender, h-index)
│       └── gpt/            # Verified citations (includes citation status, author gender, h-index)
│
├── docs/
│   ├── figures/
│   │   ├── gender/         # Figures of gender bias
│   │   ├── hallucination/  # Figures of hallucination rates
│   │   └── productivity/   # Figures of productivity (h-index)
│   ├── slides/           # Slide PNGs summarizing our project
│   ├── methodology.md    # Detailed project methodology
│   ├── references.md     # References and tools used
│   ├── result_calcs.md   # Formulas for result calculations
│   └── slides.md         # Slides viewing
│
├── src/
│   ├── generate-data/        # Scripts for data generation
│   ├── verify-analyze-data/  # Scripts for citation analysis
│   └── consolidate_data.py   # Generates CSV of relevant data points
│
├── README.md             # Project overview
└── requirements.txt      # Python dependencies
```


## Using the Data  
The data used in this project is available under `data/`.  

The dataset contains published paper abstracts, LLM-generated questions, LLM-generated citations, citation verification results, and author-level data (e.g. gender and h-index).  

To use the data, clone this repository:  
  ```bash
    git clone https://github.com/jellizz/jhmz-altREU
    cd jhmz-altREU
  ```
See our [methodology page](docs/methodology.md) for details on how our data was collected.  


## Reproducing This Experiment  
To reproduce this experiment, clone this repository and download the necessary dependencies.  
```bash
clone https://github.com/jellizz/jhmz-altREU
cd jhmz-altREU
pip install -r requirements.txt
```
Run the scripts in `src/` for data generation, citation verification, and LLM-response analysis.  Update the input and output file paths as necessary. Most can be found at the bottom of the scripts.  


## References
View references [here](docs/references.md).
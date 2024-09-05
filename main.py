import pandas as pd
import numpy as np
import xlrd
from fuzzywuzzy.fuzz import ratio
from fuzzywuzzy import process
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel,Field
import uvicorn
from collections import defaultdict,Counter
from typing import List, Union, Optional
from skill_database import SKILL_DATABASE

load_dotenv()

app = FastAPI()
collegedunia_data = pd.read_excel('CollegeDuniaRatingss.xls', engine='xlrd')
glasdoor_data = pd.read_excel('GlasdoorInformation.xls', engine='xlrd')

class Education(BaseModel):
    Degree: str
    Specialization: Optional[str] = None
    Institute: str
    Start: Union[int, str]
    End: Union[int, str]

class Experience(BaseModel):
    Company_name: str = Field(alias="Company Name")
    Designation: str
    Start: Union[int, str]
    End: Union[int, str]
    Description: List[str]


class ResumeData(BaseModel):
    Name: str
    Email: str
    phone_number: str = Field(alias="Phone-Number")
    Summary: str
    current_location: str = Field(alias="Current-Location")
    current_company: str = Field(alias="Current-Company")
    Skills: List[str]
    linkedin_id: str = Field(alias="Linkedin-Id")
    github_id: str = Field(alias="Github-Id")
    total_experience: float = Field(alias="Total-Experience")
    Education: List[Education]
    education_year: List[Union[int, str]] = Field(alias="Education-Year")
    Experiences: List[Experience]
    Projects: List
    roles_responsibility: List[str] = Field(alias="Roles-Responsibility")
    Certifications: List[str]

class Resume(BaseModel):
    resume_data: ResumeData

def score_experience(years):
    if years > 10:
        return 100
    elif years > 5:
        return 80
    elif years > 2:
        return 60
    return 40

def get_college_rating(college_name, collegedunia_data):
    max_ratio = 0
    college_rating = 0
    for index, row in collegedunia_data.iterrows():
        data_college_name = row["Title"]
        current_ratio = ratio(str(college_name), str(data_college_name))
        if current_ratio > max_ratio:
            max_ratio = current_ratio
            college_rating = row["Rating"]
    return college_rating * 10

def get_company_rating(company_name, glasdoor_data):
    max_ratio = 0
    company_rating = 0
    for index, row in glasdoor_data.iterrows():
        data_company_name = row["Company Name"]
        current_ratio = ratio(str(company_name), str(data_company_name))
        if current_ratio > max_ratio:
            max_ratio = current_ratio
            company_rating = row["Rating"]
    return company_rating * 10

def score_skills(skills, field):
    if field not in SKILL_DATABASE:
        return 0  
    
    field_skills = SKILL_DATABASE[field]
    total_score = 0
    skill_counts = defaultdict(int)
    
    for skill in skills:
        skill = skill.lower()
        best_match = process.extractOne(skill, 
                                        [s.lower() for tier in field_skills.values() for s in tier.keys()],
                                        score_cutoff=80)
        
        if best_match:
            matched_skill = best_match[0].title()
            for tier, tier_skills in field_skills.items():
                if matched_skill in tier_skills:
                    score = tier_skills[matched_skill]
                    total_score += score
                    skill_counts[tier] += 1
                    break
        else:
            words = skill.split()
            if len(words) > 1:  
                total_score += 5
                skill_counts['unknown_specific'] += 1
            else:
                total_score += 3
                skill_counts['unknown_general'] += 1
    unique_tiers = len([count for count in skill_counts.values() if count > 0])
    if unique_tiers >= 3:
        total_score *= 1.1
    unknown_skill_count = skill_counts['unknown_specific'] + skill_counts['unknown_general']
    if unknown_skill_count > 0:
        total_score *= (1 + 0.02 * unknown_skill_count)  
    normalized_score = min(total_score / len(skills) * 10, 100)
    
    return round(normalized_score, 2)

def determine_field(skills, SKILL_DATABASE):
    skill_set = set(skill.lower() for skill in skills)
    field_scores = {}

    for field, categories in SKILL_DATABASE.items():
        field_skill_set = set(skill.lower() for category in categories.values() for skill in category)
        matching_skills = skill_set.intersection(field_skill_set)
        field_scores[field] = len(matching_skills)

    best_field = max(field_scores, key=field_scores.get)
    if list(field_scores.values()).count(field_scores[best_field]) > 1:
        tied_fields = [f for f, score in field_scores.items() if score == field_scores[best_field]]
        weighted_scores = {}
        for field in tied_fields:
            score = 0
            for skill in skill_set:
                for category, category_skills in SKILL_DATABASE[field].items():
                    category_skills_lower = {k.lower(): v for k, v in category_skills.items()}
                    if skill in category_skills_lower:
                        weight = {'niche': 3, 'important': 2, 'common': 1}[category]
                        score += weight * category_skills_lower[skill]
            weighted_scores[field] = score
        best_field = max(weighted_scores, key=weighted_scores.get)

    return best_field

def calculate_overall_rating(resume_data):
    experience = resume_data.total_experience 
    college_name = resume_data.Education[0].Institute
    current_company = resume_data.current_company 
    skills = ','.join(resume_data.Skills)
    
    field = determine_field(resume_data.Skills, SKILL_DATABASE)

    experience_score = score_experience(experience)
    college_rating = get_college_rating(college_name, collegedunia_data)
    company_rating = get_company_rating(current_company, glasdoor_data)
    skills_score = score_skills(skills, field)

    overall_score = (experience_score + college_rating + company_rating + skills_score) / 4

    return {
        "experience_score": experience_score,
        "college_rating": college_rating,
        "company_rating": company_rating,
        "skills_score": skills_score,
        "overall_score": round(overall_score, 2)
    }

@app.post("/rate_resume")
def rate_resume(resume: Resume):
    try:
        resume_data = resume.resume_data
        ratings = calculate_overall_rating(resume_data)
        return ratings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)

from fastapi import FastAPI
import pickle
import sklearn

app= FastAPI()

df=pickle.load(open('movies.pkl','rb'))

model=pickle.load(open('model.pkl','rb'))
vectors=pickle.load(open('vectors.pkl','rb'))

movies_list=df['title'].tolist()

@app.get("/movies")
def get_movies():
    return movies_list

@app.post("/recommend")
def recommend(movie):
    movie_index = df[df['title'] == movie].index[0]

    distances, indices = model.kneighbors(
        vectors[movie_index:movie_index+1],
        n_neighbors=6
    )

    result=[]

    for i in indices[0][1:]:
        result.append({df.iloc[i]['title'],df.iloc[i]['poster_path']}) 
    
    return result
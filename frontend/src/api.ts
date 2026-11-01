import axios from "axios";

export const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ||
    (import.meta.env.PROD
        ? "https://envshare-backend.onrender.com/api"
        : "http://localhost:8000/api");

export const api = axios.create({
    baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
    const token = localStorage.getItem("token");
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});
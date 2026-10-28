export interface User {
    id: string;
    name: string;
    email: string;
}

export interface Environment {
    id: string;
    name: string;
}

export interface Project {
    id: string;
    name: string;
    description?: string;
    role: string;
    environments: Environment[];
}

export interface VariableItem {
    id: string;
    key: string;
    value: string;
    is_sensitive: boolean;
    updated_at: string;
}

export interface DiffItem {
    key: string;
    old_value: string | null;
    new_value: string;
    status: "NEW" | "UPDATE" | "UNCHANGED";
    is_sensitive: boolean;
}

export interface HistoryItem {
    id: string;
    action: string;
    key: string | null;
    old_value: string | null;
    new_value: string | null;
    user_name: string;
    created_at: string;
}
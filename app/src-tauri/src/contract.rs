use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ErrorCode {
    InvalidTask,
    UnknownAction,
    InputNotFound,
    WrongPassword,
    DependencyMissing,
    BinaryNotFound,
    Cancelled,
    Timeout,
    ConversionFailed,
    Internal,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProcessorTask {
    pub id: String,
    pub engine: String,
    pub action: String,
    pub input_files: Vec<String>,
    pub output_dir: String,
    #[serde(default)]
    pub options: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum TaskEvent {
    #[serde(rename = "progress")]
    Progress {
        id: String,
        percent: f64,
        #[serde(default)]
        message: Option<String>,
    },
    #[serde(rename = "log")]
    Log {
        id: String,
        level: String,
        message: String,
    },
    #[serde(rename = "result")]
    Result {
        id: String,
        status: String,
        #[serde(rename = "outputFiles")]
        output_files: Vec<String>,
        #[serde(default)]
        meta: Option<serde_json::Value>,
    },
    #[serde(rename = "error")]
    Error {
        id: String,
        code: ErrorCode,
        message: String,
        #[serde(default)]
        details: Option<String>,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct EngineStatus {
    pub available: bool,
    pub version: Option<String>,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct EngineHealth {
    pub engines: HashMap<String, EngineStatus>,
}

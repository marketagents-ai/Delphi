from pydantic import BaseModel, Field
from typing import Union

class InputSchema(BaseModel):
    func_name: str
    func_input_data: Union[list, str]

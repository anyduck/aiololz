import base64
from abc import ABC, abstractmethod
from io import BytesIO

import matplotlib.pyplot as plt
import numpy as np
import tflite_runtime.interpreter as tflite
from matplotlib.backend_bases import MouseEvent
from PIL import Image


class AbstractSolver(ABC):

    @abstractmethod
    def solve(self, image_encoded: str, grid_size: int) -> tuple[int, int]:
        """ Find cell with circle in a base64 encoded image. """

    def _read_base64_image(self, image_encoded: str) -> Image.Image:

        return Image.open(BytesIO(base64.b64decode(image_encoded)))


class ManualSolver(AbstractSolver):
    def __init__(self):
        self._x, self._y = .0, .0

    def plot(self, image: Image.Image, grid_size: int):
        w, h = image.size
        plt.imshow(image)
        plt.gca().set_xticks(range(0, w, grid_size))
        plt.gca().set_yticks(range(0, h, grid_size))
        plt.grid()

    def solve(self, image_encoded: str, grid_size: int) -> tuple[int, int]:
        image = self._read_base64_image(image_encoded)

        plt.connect('button_press_event', self.on_click)
        self.plot(image, grid_size)
        plt.show()

        return int(self._x / grid_size), int(self._y / grid_size)

    def on_click(self, event: MouseEvent):
        x, y = event.xdata, event.ydata
        if x is not None and y is not None:
            self._x, self._y = x, y
            plt.close()


class TensorflowSolver(AbstractSolver):
    def __init__(self, model_path, grid_size):
        self._interpreter = tflite.Interpreter(str(model_path))
        # TODO - dynamic batch size
        self._interpreter.resize_tensor_input(0, [120, 20, 20, 3])
        self._interpreter.allocate_tensors()
        self._input = self._interpreter.get_input_details()[0]
        self._output = self._interpreter.get_output_details()[0]
        self._grid_size = grid_size

    def solve(self, image_encoded: str, grid_size: int) -> tuple[int, int]:
        assert grid_size == self._grid_size

        image = self._read_base64_image(image_encoded)
        batch = self._split_image(image, grid_size)

        result = self._get_pobabilities(batch)

        max_prob = 0
        index = 0
        for i, res in enumerate(result):
            if res[1] > max_prob:
                max_prob = res[1]
                index = i
        return index // 10, index % 10

    def _split_image(self, image: Image.Image, grid_size: int) -> np.ndarray:
        data = []
        for i in range(0, image.width, grid_size):
            for j in range(0, image.height, grid_size):
                sub_image = image.crop([i, j, i + grid_size, j + grid_size])
                data.append(np.array(sub_image, dtype=np.float32))
        return np.array(data, dtype=np.float32)

    def _get_pobabilities(self, batch: np.ndarray):
        self._interpreter.set_tensor(self._input['index'], batch)
        self._interpreter.invoke()
        return self._interpreter.get_tensor(self._output['index'])


if __name__ == '__main__':
    debug_data = 'dafa'
    solver = ManualSolver()
    res = solver.solve(debug_data, 20)

    print(res)

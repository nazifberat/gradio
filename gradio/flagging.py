import gradio as gr
import os
import datetime
from gradio import encryptor
import csv
import io
from abc import ABC, abstractmethod


class FlaggingCallback(ABC):
    """
    An abstract class for defining the methods that any FlaggingCallback should have.
    """

    @abstractmethod
    def setup(self, flagging_dir):
        """
        This method should be overridden and ensure that everything is set up correctly for flag().
        This method gets called once at the beginning of the Interface.launch() method.
        Parameters:
        flagging_dir: A string, typically containing the path to the directory where the flagging file should be storied (provided as an argument to Interface.__init__()).
        """
        pass

    @abstractmethod
    def flag(self, interface, input_data, output_data, flag_option=None, flag_index=None, username=None):
        """
        This method should be overridden by the FlaggingCallback subclass and may contain optional additional arguments.
        This gets called every time the <flag> button is pressed.
        Parameters:
        interface: The Interface object that is being used to launch the flagging interface.
        input_data: The input data to be flagged.
        output_data: The output data to be flagged.        
        flag_option (optional): In the case that flagging_options are provided, the flag option that is being used.
        flag_index (optional): The index of the sample that is being flagged.
        username (optional): The username of the user that is flagging the data, if logged in.
        Returns:
        (int) The total number of samples that have been flagged.
        """
        pass


class SimpleCSVLogger(FlaggingCallback):
    """
    A simple example implementation of the FlaggingCallback abstract class provided for illustrative purposes
    """
    def setup(self, flagging_dir):
        self.flagging_dir = flagging_dir
        os.makedirs(flagging_dir, exist_ok=True)

    def flag(self, interface, input_data, output_data, flag_option=None, flag_index=None, username=None):
        flagging_dir = self.flagging_dir
        log_filepath = "{}/log.csv".format(flagging_dir)

        csv_data = []
        for i, input in enumerate(interface.input_components):
            csv_data.append(input.save_flagged(
                flagging_dir, interface.config["input_components"][i]["label"], input_data[i], None))
        for i, output in enumerate(interface.output_components):
            csv_data.append(output.save_flagged(
                flagging_dir, interface.config["output_components"][i]["label"], output_data[i], None) if
                            output_data[i] is not None else "")
        
        with open(log_filepath, "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(csv_data)
        
        with open(log_filepath, "r") as csvfile:
            line_count = len([None for row in csv.reader(csvfile)]) - 1
        return line_count


class CSVLogger(FlaggingCallback):
    """
    The default implementation of the FlaggingCallback abstract class. Logs the input and output data to a CSV file.
    """
    def setup(self, flagging_dir):
        self.flagging_dir = flagging_dir
        os.makedirs(flagging_dir, exist_ok=True)

    def flag(self, interface, input_data, output_data, flag_option=None, flag_index=None, username=None):
        flagging_dir = self.flagging_dir
        log_fp = "{}/log.csv".format(flagging_dir)
        encryption_key = interface.encryption_key if interface.encrypt else None
        is_new = not os.path.exists(log_fp)

        if flag_index is None:
            csv_data = []
            for i, input in enumerate(interface.input_components):
                csv_data.append(input.save_flagged(
                    flagging_dir, interface.config["input_components"][i]["label"], input_data[i], encryption_key))
            for i, output in enumerate(interface.output_components):
                csv_data.append(output.save_flagged(
                    flagging_dir, interface.config["output_components"][i]["label"], output_data[i], encryption_key) if
                                output_data[i] is not None else "")
            if flag_option is not None:
                csv_data.append(flag_option)
            if username is not None:
                csv_data.append(username)
            csv_data.append(str(datetime.datetime.now()))
            if is_new:
                headers = [interface["label"]
                           for interface in interface.config["input_components"]]
                headers += [interface["label"]
                            for interface in interface.config["output_components"]]
                if interface.flagging_options is not None:
                    headers.append("flag")
                if username is not None:
                    headers.append("username")
                headers.append("timestamp")

        def replace_flag_at_index(file_content):
            file_content = io.StringIO(file_content)
            content = list(csv.reader(file_content))
            header = content[0]
            flag_col_index = header.index("flag")
            content[flag_index][flag_col_index] = flag_option
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerows(content)
            return output.getvalue()

        if interface.encrypt:
            output = io.StringIO()
            if not is_new:
                with open(log_fp, "rb") as csvfile:
                    encrypted_csv = csvfile.read()
                    decrypted_csv = encryptor.decrypt(
                        interface.encryption_key, encrypted_csv)
                    file_content = decrypted_csv.decode()
                    if flag_index is not None:
                        file_content = replace_flag_at_index(file_content)
                    output.write(file_content)
            writer = csv.writer(output)
            if flag_index is None:
                if is_new:
                    writer.writerow(headers)
                writer.writerow(csv_data)
            with open(log_fp, "wb") as csvfile:
                csvfile.write(encryptor.encrypt(
                    interface.encryption_key, output.getvalue().encode()))
        else:
            if flag_index is None:
                with open(log_fp, "a", newline="") as csvfile:
                    writer = csv.writer(csvfile)
                    if is_new:
                        writer.writerow(headers)
                    writer.writerow(csv_data)
            else:
                with open(log_fp) as csvfile:
                    file_content = csvfile.read()
                    file_content = replace_flag_at_index(file_content)
                with open(log_fp, "w", newline="") as csvfile:  # newline parameter needed for Windows
                    csvfile.write(file_content)
        with open(log_fp, "r") as csvfile:
            line_count = len([None for row in csv.reader(csvfile)]) - 1
        return line_count


class HuggingFaceDatasetSaver(FlaggingCallback):
    """
    An alternative FlaggingCallback that saves the data to a HuggingFace dataset.
    """
    def __init__(self, hf_foken, dataset_name, organization=None, private=False):
        """
        Params:
        hf_token (str): The token to use to access the huggingface API.
        dataset_name (str): The name of the dataset to save the data to, e.g. "abidlabs/image-classifier-1"
        organization (str): The name of the organization to which to attach the datasets
        private (optional): If the dataset does not already exist, whether it should be created as a private dataset or public. 
            Private datasets may require paid huggingface.co accounts

        """
        self.hf_foken = hf_foken
        self.dataset_name = dataset_name
        self.organization_name = organization
        self.dataset_private = private

    def setup(self, flagging_dir):
        """
        Params:
        flagging_dir (str): local directory where the dataset is cloned, updated, and pushed from
        """
        try:
            import huggingface_hub 
        except (ImportError, ModuleNotFoundError):
            raise ImportError("Package `huggingface_hub` not found is needed for HuggingFaceDatasetSaver. Try 'pip install huggingface_hub'.")
        huggingface_hub.create_repo(name=self.dataset_name, token=self.hf_foken, private=self.dataset_private, repo_type="dataset", exist_ok=True)
        dataset_repo_url = "https://huggingface.co/datasets/{}".format(self.dataset_name)
        self.flagging_dir = flagging_dir
        self.repo = huggingface_hub.Repository(local_dir=flagging_dir, clone_from=dataset_repo_url, use_auth_token=self.hf_foken)
        self.log_file = os.path.join(flagging_dir, "data.csv")  # TODO(abidlabs): should filename be user-specified?


    def flag(self, interface, input_data, output_data, flag_option=None, flag_index=None, username=None, path=None):
        import huggingface_hub
        
        is_new = not os.path.exists(self.log_file)
        with open(self.log_file, "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            
            # Generate the headers
            headers = [interface["label"] for interface in interface.config["input_components"]]
            headers += [interface["label"] for interface in interface.config["output_components"]]
            if interface.flagging_options is not None:
                headers.append("flag")
            
            # Generate the row corresponding to the flagged sample
            csv_data = []
            for i, input in enumerate(interface.input_components):
                csv_data.append(input.save_flagged(self.flagging_dir, interface.config["input_components"][i]["label"], input_data[i], None))
            for i, output in enumerate(interface.output_components):
                csv_data.append(output.save_flagged(self.flagging_dir, interface.config["output_components"][i]["label"], output_data[i], None) if
                    output_data[i] is not None else "")
            if flag_option is not None:
                csv_data.append(flag_option)
            
            # Write the rows
            if is_new:
                writer.writerow(headers)
            writer.writerow(csv_data)
        
        # push the repo 
        self.repo.push_to_hub()

        # return number of samples in dataset
        with open(self.log_file, "r") as csvfile:
            line_count = len([None for row in csv.reader(csvfile)]) - 1
        
        return line_count

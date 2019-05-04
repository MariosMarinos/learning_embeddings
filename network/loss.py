import torch
from torch import nn
from data.db import ETHECLabelMap, ETHECLabelMapMergedSmall

class MultiLevelCELoss(torch.nn.Module):
    def __init__(self, labelmap, level_weights=None, weight=None):
        torch.nn.Module.__init__(self)
        self.labelmap = labelmap
        self.level_weights = [1.0] * len(self.labelmap.levels) if level_weights is None else level_weights
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.criterion = []
        if weight is None:
            for level_len in self.labelmap.levels:
                self.criterion.append(nn.CrossEntropyLoss(weight=None, reduction='none'))
        else:
            level_stop, level_start = [], []
            for level_id, level_len in enumerate(self.labelmap.levels):
                if level_id == 0:
                    level_start.append(0)
                    level_stop.append(level_len)
                else:
                    level_start.append(level_stop[level_id - 1])
                    level_stop.append(level_stop[level_id - 1] + level_len)
                self.criterion.append(nn.CrossEntropyLoss(weight=weight[level_start[level_id]:level_stop[level_id]].to(self.device),
                                                          reduction='none'))

        print('==Using the following weights config for multi level cross entropy loss: {}'.format(self.level_weights))

    def forward(self, outputs, labels, level_labels):
        loss = 0.0
        for level_id, level in enumerate(self.labelmap.levels):
            if level_id == 0:
                loss += self.level_weights[level_id] * self.criterion[level_id](outputs[:, 0:level], level_labels[:, level_id])
            else:
                start = sum([self.labelmap.levels[l_id] for l_id in range(level_id)])
                loss += self.level_weights[level_id] * self.criterion[level_id](outputs[:, start:start + level],
                                                                          level_labels[:, level_id])
        return torch.mean(loss)


class LastLevelCELoss(torch.nn.Module):
    def __init__(self, labelmap, level_weights=None, weight=None):
        torch.nn.Module.__init__(self)
        self.labelmap = labelmap
        self.level_weights = [1.0] * len(self.labelmap.levels) if level_weights is None else level_weights
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.criterion = []
        self.softmax = torch.nn.Softmax(dim=1)

        self.level_stop, self.level_start = [], []
        for level_id, level_len in enumerate(self.labelmap.levels):
            if level_id == 0:
                self.level_start.append(0)
                self.level_stop.append(level_len)
            else:
                self.level_start.append(self.level_stop[level_id - 1])
                self.level_stop.append(self.level_stop[level_id - 1] + level_len)

        if weight is None:
            for level_len in self.labelmap.levels:
                self.criterion.append(nn.NLLLoss(weight=None, reduction='none'))
        else:
            self.criterion.append(nn.NLLLoss(weight=weight[self.level_start[level_id]:self.level_stop[level_id]].to(self.device),
                                                      reduction='none'))

        print('==Using the following weights config for last level cross entropy loss: {}'.format(self.level_weights))

    def forward(self, outputs, labels, level_labels):
        # print(outputs)
        # print(level_labels)
        outputs_new = torch.zeros((outputs.shape[0], self.labelmap.n_classes))
        # print("outputs_new", outputs_new)
        outputs_new[:, self.level_start[-1]:self.level_stop[-1]] = self.softmax(outputs[:, :])
        # print("outputs_new", outputs_new)
        for level_index in range(len(self.labelmap.levels)-2, -1, -1):
            # print("--"*30)
            # print("level_index: {}, level len: {}".format(level_index, self.labelmap.levels[level_index]))
            # print("getting child of: {}".format(self.labelmap.level_names[level_index]))
            child_of = getattr(self.labelmap, "child_of_{}_ix".format(self.labelmap.level_names[level_index]))
            for parent_ix in child_of:
                # print("==== parent_ix: {} children: {}".format(parent_ix, child_of[parent_ix]))
                # print("will sum these: {}".format(outputs_new[:, self.level_start[level_index+1]+torch.tensor(child_of[parent_ix])]))
                # print("sum: {}".format(torch.sum(outputs_new[:, self.level_start[level_index+1]+torch.tensor(child_of[parent_ix])], dim=1)))
                outputs_new[:, self.level_start[level_index]+torch.tensor(parent_ix)] = \
                    torch.sum(outputs_new[:, self.level_start[level_index+1]+torch.tensor(child_of[parent_ix])], dim=1)
                # print("outputs_new", outputs_new)

        loss = 0.0
        for level_id, level in enumerate(self.labelmap.levels):
            if level_id == 0:
                # print("outputs level {}: {}".format(level_id, outputs_new[:, 0:level]))
                loss += self.level_weights[level_id] * self.criterion[level_id](torch.log(outputs_new[:, 0:level]), level_labels[:, level_id])
            else:
                start = sum([self.labelmap.levels[l_id] for l_id in range(level_id)])
                # print("outputs level {}: {}".format(level_id, outputs_new[:, start:start + level]))
                loss += self.level_weights[level_id] * self.criterion[level_id](torch.log(outputs_new[:, start:start + level]),
                                                                          level_labels[:, level_id])
        return outputs_new, torch.mean(loss)


class MultiLabelSMLoss(torch.nn.MultiLabelSoftMarginLoss):
    def __init__(self, weight=None, size_average=None, reduce=None, reduction='mean'):
        print(weight)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if weight is not None:
            weight = weight.to(self.device)
        torch.nn.MultiLabelSoftMarginLoss.__init__(self, weight, size_average, reduce, reduction)

    def forward(self, outputs, labels, level_labels):
        return super().forward(outputs, labels)


if __name__ == '__main__':
    lmap = ETHECLabelMap()
    criterion = MultiLevelCELoss(labelmap=lmap, level_weights=[1, 1, 1, 1])
    output, level_labels = torch.zeros((1, lmap.n_classes)), torch.tensor([[0,
                                                                            7-lmap.levels[0],
                                                                            90-(lmap.levels[0]+lmap.levels[1]),
                                                                            400-(lmap.levels[0]+lmap.levels[1]+lmap.levels[2])]])
    labels = torch.zeros((1, lmap.n_classes))
    labels[0, torch.tensor([0, 7, 90, 400])] = 1
    output[:, 0] = 100
    output[:, 7] = 100
    output[:, 90] = 10000
    output[:, 400] = 10000
    print(output)
    print(labels)
    print(level_labels)
    print('MLCELoss: {}'.format(criterion(output, labels, level_labels)))

    criterion_multi_label = torch.nn.MultiLabelSoftMarginLoss()
    custom_criterion_multi_label = MultiLabelSMLoss()
    print('MLSMLoss: {}'.format(criterion_multi_label(output, labels)))
    print('MLSMLoss: {}'.format(custom_criterion_multi_label(output, labels, level_labels)))

    print("="*30)
    torch.manual_seed(0)

    lmap = ETHECLabelMapMergedSmall()
    criterion = LastLevelCELoss(labelmap=lmap)
    print("Labelmap levels: {}".format(lmap.levels))

    outputs, level_labels = torch.rand((2, lmap.levels[-1])), torch.tensor([[0, 0, 0, 0], [0, 0, 0, 0]])

    print(criterion(outputs, None, level_labels))



import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.model_zoo as model_zoo
import torchvision.models as models
from collections import OrderedDict
from densenet import _DenseLayer, _DenseBlock, _Transition

__all__ = ['DenseNet', 'densenet169']

usingVGG=False
useMaxPool=False

model_urls = {
    'densenet169': 'https://download.pytorch.org/models/densenet169-b2777c0a.pth',
}

def densenet169(pretrained=False, **kwargs):
    r"""Densenet-169 model from
    `"Densely Connected Convolutional Networks" <https://arxiv.org/pdf/1608.06993.pdf>`_

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
    """
    model = MultiViewDenseNet(num_init_features=64, growth_rate=32, block_config=(6, 12, 32, 32),
                     **kwargs)
    if pretrained:
        model.load_state_dict(model_zoo.load_url(model_urls['densenet169']), strict=False)
    return model

# class _DenseLayer(nn.Sequential):
#     def __init__(self, num_input_features, growth_rate, bn_size, drop_rate):
#         super(_DenseLayer, self).__init__()
#         self.add_module('norm1', nn.BatchNorm2d(num_input_features)),
#         self.add_module('relu1', nn.ReLU(inplace=True)),
#         self.add_module('conv1', nn.Conv2d(num_input_features, bn_size *
#                         growth_rate, kernel_size=1, stride=1, bias=False)),
#         self.add_module('norm2', nn.BatchNorm2d(bn_size * growth_rate)),
#         self.add_module('relu2', nn.ReLU(inplace=True)),
#         self.add_module('conv2', nn.Conv2d(bn_size * growth_rate, growth_rate,
#                         kernel_size=3, stride=1, padding=1, bias=False)),
#         self.drop_rate = drop_rate
#
#     def forward(self, x):
#         new_features = super(_DenseLayer, self).forward(x)
#         if self.drop_rate > 0:
#             new_features = F.dropout(new_features, p=self.drop_rate, training=self.training)
#         return torch.cat([x, new_features], 1)
#
#
# class _DenseBlock(nn.Sequential):
#     def __init__(self, num_layers, num_input_features, bn_size, growth_rate, drop_rate):
#         super(_DenseBlock, self).__init__()
#         for i in range(num_layers):
#             layer = _DenseLayer(num_input_features + i * growth_rate, growth_rate, bn_size, drop_rate)
#             self.add_module('denselayer%d' % (i + 1), layer)
#
#
# class _Transition(nn.Sequential):
#     def __init__(self, num_input_features, num_output_features):
#         super(_Transition, self).__init__()
#         self.add_module('norm', nn.BatchNorm2d(num_input_features))
#         self.add_module('relu', nn.ReLU(inplace=True))
#         self.add_module('conv', nn.Conv2d(num_input_features, num_output_features,
#                                           kernel_size=1, stride=1, bias=False))
#         self.add_module('pool', nn.AvgPool2d(kernel_size=2, stride=2))


class MultiViewDenseNet(nn.Module):
    r"""Densenet-BC model class, based on
    `"Densely Connected Convolutional Networks" <https://arxiv.org/pdf/1608.06993.pdf>`_

    Args:
        growth_rate (int) - how many filters to add each layer (`k` in paper)
        block_config (list of 4 ints) - how many layers in each pooling block
        num_init_features (int) - the number of filters to learn in the first convolution layer
        bn_size (int) - multiplicative factor for number of bottle neck layers
          (i.e. bn_size * k features in the bottleneck layer)
        drop_rate (float) - dropout rate after each dense layer
        num_classes (int) - number of classification classes
    """
    def __init__(self, growth_rate=32, block_config=(6, 12, 24, 16),
                 num_init_features=64, bn_size=4, drop_rate=0, num_classes=1000):

        super(MultiViewDenseNet, self).__init__()

        # First convolution
        self.features = nn.Sequential(OrderedDict([
            ('conv0', nn.Conv2d(3, num_init_features, kernel_size=7, stride=2, padding=3, bias=False)),
            ('norm0', nn.BatchNorm2d(num_init_features)),
            ('relu0', nn.ReLU(inplace=True)),
            ('pool0', nn.MaxPool2d(kernel_size=3, stride=2, padding=1)),
        ]))

        # Each denseblock
        num_features = num_init_features
        for i, num_layers in enumerate(block_config):
            block = _DenseBlock(num_layers=num_layers, num_input_features=num_features,
                                bn_size=bn_size, growth_rate=growth_rate, drop_rate=drop_rate)
            self.features.add_module('denseblock%d' % (i + 1), block)
            num_features = num_features + num_layers * growth_rate
            if i != len(block_config) - 1:
                trans = _Transition(num_input_features=num_features, num_output_features=num_features // 2)
                self.features.add_module('transition%d' % (i + 1), trans)
                num_features = num_features // 2

        # Final batch norm
        self.features.add_module('norm5', nn.BatchNorm2d(num_features))

        # Linear layer
        # self.classifier = nn.Linear(num_features, 1000)
        # self.fc = nn.Linear(1000, 1)
        # self.net2 = nn.Sequential(
        #         nn.Conv2d(num_features,num_features,kernel_size=3),
        #         nn.Conv2d(num_features,num_features,kernel_size=2,stride=2),
        #         nn.Conv2d(num_features,num_features,kernel_size=2)
        #         )
        self.resizer = nn.Conv2d(1664,512,kernel_size=3,padding=1)

        self.net2 = models.vgg16(pretrained=True).classifier
        if usingVGG:
            self.net2 = models.vgg16(pretrained=True).classifier
            self.fc=nn.Linear(1000,1)
        else:
            self.net2 = nn.Sequential(
                    nn.Conv2d(num_features,num_features,kernel_size=3),
                    nn.Conv2d(num_features,num_features,kernel_size=2,stride=2),
                    nn.Conv2d(num_features,num_features,kernel_size=2)
                    )
            self.fc = nn.Linear(num_features, 1)

        # Official init from torch repo.
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal(m.weight.data)
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
            elif isinstance(m, nn.Linear):
                m.bias.data.zero_()

    def forward(self, x):
        features = self.features(x)
        out = F.relu(features, inplace=True) #(N,1664,7,7)
        # print("Out shape after relu: ",out.shape)

        if useMaxPool:
            out = torch.max(out,0)[0].unsqueeze(0) #(1,1664,7,7)
        else: #use avgpool
            out = torch.mean(out,0,keepdim=True)

        if not usingVGG:
            out = self.net2(out)
            out = out.squeeze()
        else:
            #print("out shape after ViewPool:", out.shape)
            out = self.resizer(out)
            #print("out shape after resizing:", out.shape)
            out = self.net2(out.view((out.shape[0],-1))).view((out.shape[0],-1))
            #print("out shape after net2:", out.shape)
        #out = F.avg_pool2d(out, kernel_size=7, stride=1).view(features.size(0), -1) #(N,1664)
        # out = F.relu(self.classifier(out))
        out = F.sigmoid(self.fc(out))
        # print("End of iter")
        return out

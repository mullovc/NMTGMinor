import onmt
import onmt.modules
import torch.nn as nn
import torch, math

from torch.nn.modules.loss import _Loss
import torch.nn.functional as F
from onmt.modules.Loss import LossFuncBase
from collections import defaultdict
from onmt.modules.Loss import NMTLossFunc


class NMTL2Loss(NMTLossFunc):
    """
    Extending the typical cross entropy loss
    """

    def forward(self, output_dict, targets, generator=None, backward=False,
                tgt_mask=None, normalizer=1, params=None, **kwargs):
        """
        Compute the loss. Subclass must define this method.
        Args:
            output_dict: the predictive output from the model. time x batch x vocab_size
                                                   or time x batch x hidden_size
            targets: the validate target to compare output with. time x batch
            backward
            tgt_mask: for masking the target (saving memory)
            generator: in case we want to save memory and
            normalizer: the denomination term of the loss
            params: a dictionary of additional parameters required for computing loss function
            **kwargs(optional): additional info for computing loss.
        """

        outputs = output_dict['hiddens']
        # tgt_outputs = output_dict['tgt_hiddens']

        attn_outs = output_dict['attn_outs']
        tgt_attn_outs = output_dict['tgt_attn_outs']
        mask = tgt_mask
        # flatten the output
        outputs = outputs.contiguous().view(-1, outputs.size(-1))
        # tgt_outputs = tgt_outputs.contiguous().view(-1, tgt_outputs.size(-1))
        targets = targets.view(-1)

        if params is None:
            params = defaultdict(lambda: 0.0)

        assert(mask is not None), "* Padding is required to mask the hidden states correctly"

        if mask is not None:
            """ We remove all positions with PAD 
                to save memory on unwanted positions
            """
            flattened_mask = mask.view(-1)

            non_pad_indices = torch.nonzero(flattened_mask).squeeze(1)

            clean_output_from_src = outputs.index_select(0, non_pad_indices)

            clean_targets = targets.index_select(0, non_pad_indices)

            # clean_output_from_tgt = tgt_outputs.index_select(0, non_pad_indices)

            for l in [attn_outs, tgt_attn_outs]:
                for i in l:
                    l[i] = l[i].contiguous().view(-1, l[i].size(-1))

                    l[i] = l[i].index_select(0, non_pad_indices)

            # L x (B) x H (B) is the filtered batch size
            attn_outs_ = torch.stack([attn_outs[i] for i in attn_outs])
            tgt_attn_outs_ = torch.stack([tgt_attn_outs[i] for i in tgt_attn_outs])

            # normalize
            shape = (attn_outs_.size(-1), )
            normalized_shape = torch.Size(shape)
            attn_outs_ = F.layer_norm(attn_outs_, normalized_shape, None, None, 1e-5)

            tgt_attn_outs_ = F.layer_norm(tgt_attn_outs_, normalized_shape, None, None, 1e-5)

            n_layers = len(attn_outs)

        else:
            # print("* Padding is required to mask the hidden ")
            raise NotImplementedError
            clean_output_from_src = outputs
            clean_targets = targets
            # clean_output_from_tgt = tgt_outputs

        dists_from_src = generator(clean_output_from_src)

        # dists_from_tgt = generator(clean_output_from_tgt)

        loss, loss_data = self._compute_loss(dists_from_src, clean_targets)

        # l2_loss = (clean_output_from_src.float() - clean_output_from_tgt.float()) ** 2
        l2_loss = ((attn_outs_.float() - tgt_attn_outs_.float()) ** 2) / n_layers
        l2_loss = l2_loss.sum()

        loss = loss + params['l2'] * l2_loss

        if backward:
            loss.div(normalizer).backward()

        output = defaultdict(lambda: None)
        output['loss'] = loss
        output['nll'] = loss_data
        output['l2_target'] = l2_loss.item()

        return output
